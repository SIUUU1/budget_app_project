"""서비스 계층
"""

from __future__ import annotations

import calendar  # 달력 계산 (2월이 28일인지 29일인지 등)
import csv       # CSV 파일 읽기/쓰기
import os
import shutil    # 파일 복사 (백업에 사용)
from datetime import datetime
from typing import Iterator, Optional

from .errors import CategoryError, NotFoundError, ValidationError
from .models import (
    RecurringRule,
    Transaction,
    validate_amount,
    validate_date,
    validate_day,
    validate_month,
    validate_type,
)
from .repository import (
    BudgetStore,
    CategoryStore,
    RecurringStore,
    TransactionRepository,
)

# import/export 로 주고받는 CSV 의 열 순서.
CSV_HEADER: list[str] = ["date", "type", "category", "amount", "memo", "tags"]


class BudgetService:
    """가계부의 모든 기능을 담은 클래스."""

    def __init__(
        self,
        tx_repo: TransactionRepository,
        cat_store: CategoryStore,
        budget_store: BudgetStore,
        recurring_store: RecurringStore,
    ) -> None:
        
        self.tx_repo = tx_repo
        self.cat_store = cat_store
        self.budget_store = budget_store
        self.recurring_store = recurring_store

    # ----------------------------- add ----------------------------------- #
    def add_transaction(
        self,
        type_: str,
        date: str,
        category: str,
        amount: object,
        memo: str = "",
        tags: Optional[list[str]] = None,
    ) -> Transaction:
        """거래 한 건을 검증한 뒤 저장한다.
        """
        # 1) 형식 검증 — 통과하면 다듬어진 값이 돌아오고, 틀리면 여기서 예외가 나며 멈춘다.
        type_ = validate_type(type_)
        date = validate_date(date)
        amount_int = validate_amount(amount)
        category = (category or "").strip()
        if not self.cat_store.exists(category):
            raise CategoryError(
                f"등록되지 않은 카테고리입니다: {category!r}",
                "'category add' 로 등록하거나 기존 카테고리를 사용하세요. "
                f"현재: {', '.join(self.cat_store.list()) or '(없음)'}",
            )
        # 2) 객체 생성 
        tx = Transaction(
            id=self.tx_repo.next_id(),
            type=type_,
            date=date,
            amount=amount_int,
            category=category,
            memo=memo or "",
            tags=tags or [],
        )
        # 3) 저장
        self.tx_repo.append(tx)
        # 4) 저장한 객체를 돌려준다 -> cli 가 "id=TX-000001" 을 출력할 수 있다.
        return tx

    # ----------------------------- list ---------------------------------- #
    def list_recent(self, limit: int) -> Iterator[Transaction]:
        """최신순으로 limit 건만 흘려보낸다.
        """
        count = 0
        for tx in self.tx_repo.iter_recent():
            if count >= limit:
                break
            yield tx
            count += 1

    # ---------------------------- search --------------------------------- #
    def search(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        category: Optional[str] = None,
        type_: Optional[str] = None,
        q: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> list[Transaction]:
        """여러 조건으로 거래를 찾는다. 조건은 전부 선택이며, 있는 것만 적용된다."""
        if type_ is not None:
            type_ = validate_type(type_)
        if date_from is not None:
            date_from = validate_date(date_from)
        if date_to is not None:
            date_to = validate_date(date_to)

        def matches(tx: Transaction) -> bool:
            """거래 하나가 모든 조건을 만족하는지 검사한다.

            내부 함수를 사용해 바깥 함수의 조건값(date_from 등)을 그대로 활용한다.
            조건 중 하나라도 만족하지 않으면 즉시 False를 반환하고,
            모든 조건을 통과하면 True를 반환한다.
            """
            if date_from and tx.date < date_from:
                return False
            if date_to and tx.date > date_to:
                return False
            if category and tx.category != category:
                return False
            if type_ and tx.type != type_:
                return False
            if q and q not in tx.memo:      # q 는 메모 '일부만' 맞아도 되는 키워드 검색
                return False
            if tag and tag not in tx.tags:  # 태그는 목록 안에 정확히 있어야 함
                return False
            return True  # 위 관문을 다 통과했으면 조건에 맞는 거래다

        results = [tx for tx in self.tx_repo.iter_all() if matches(tx)]
        # ( 날짜, id로 정렬.
        # reverse=True 는 내림차순 = 최신순.
        results.sort(key=lambda t: (t.date, t.id), reverse=True)
        return results

    # ---------------------------- summary -------------------------------- #
    def summary(self, month: str, top: int = 5) -> dict:
        """한 달치 수입/지출/잔액과 지출 TOP N 을 계산한다.
        """
        month = validate_month(month)
        total_income = 0
        total_expense = 0
        by_category: dict[str, int] = {}  # 카테고리별 지출 합계
        found = False  # 해당 달에 거래 유무

        for tx in self.tx_repo.iter_all():
            # tx.date 는 "2024-01-15" 이고 [:7] 은 앞 7글자 = "2024-01".
            if tx.date[:7] != month:
                continue  # 다른 달이면 건너뛴다
            found = True
            if tx.type == "income":
                total_income += tx.amount
            else:
                total_expense += tx.amount
                by_category[tx.category] = by_category.get(tx.category, 0) + tx.amount

        # 카테고리별 합계를 금액 큰 순으로 정렬해 앞에서 top 개만 자른다.
        # kv 는 ("food", 45000) 같은 묶음이고 kv[1] 은 금액이다.
        top_list = sorted(by_category.items(), key=lambda kv: kv[1], reverse=True)[:top]
        return {
            "month": month,
            "found": found,
            "total_income": total_income,
            "total_expense": total_expense,
            "balance": total_income - total_expense,
            "top": top_list,
            "budget": self.budget_store.get(month),
        }

    # ---------------------------- update --------------------------------- #
    def update_transaction(
        self,
        tx_id: str,
        *,
        date: Optional[str] = None,
        type_: Optional[str] = None,
        category: Optional[str] = None,
        amount: object = None,
        memo: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> Transaction:
        """거래를 찾아 지정한 항목만 수정한다.

        매개변수의 * 뒤에 오는 값은 반드시 이름을 지정해 전달해야 한다.
        이는 여러 선택적 항목의 순서를 잘못 입력해 다른 값을 수정하는 것을 방지한다.
        
        예시)
        update_transaction("TX-1", "2024-01-01") 처럼 순서로 넘기면 오류가 나고 update_transaction("TX-1", date="2024-01-01") 이라고 써야 한다.

        각 항목이 None이면 해당 항목은 수정하지 않으며,
        빈 문자열("")을 전달하면 해당 값을 빈 값으로 수정한다.
        """
        found: Optional[Transaction] = None
        new_list: list[Transaction] = []

        for tx in self.tx_repo.iter_all():
            if tx.id == tx_id:
                if date is not None:
                    tx.date = validate_date(date)
                if type_ is not None:
                    tx.type = validate_type(type_)
                if amount is not None:
                    tx.amount = validate_amount(amount)
                if category is not None:
                    category = category.strip()
                    if not self.cat_store.exists(category):
                        raise CategoryError(
                            f"등록되지 않은 카테고리입니다: {category!r}",
                            "'category add' 로 먼저 등록하세요.",
                        )
                    tx.category = category
                if memo is not None:
                    tx.memo = memo
                if tags is not None:
                    tx.tags = tags
                found = tx
            new_list.append(tx)

        if found is None:
            # 끝까지 못 찾았다면 잘못된 id 다.
            # 이 예외가 던져지면 아래 rewrite 는 실행되지 않는다.
            raise NotFoundError(
                f"존재하지 않는 id 입니다: {tx_id}",
                "'list' 로 유효한 id 를 확인하세요.",
            )
        self.tx_repo.rewrite(new_list)  # 전체 재작성 + 원자적 교체
        return found

    # ---------------------------- delete --------------------------------- #
    def delete_transaction(self, tx_id: str) -> None:
        """거래 하나를 지운다.
        """
        kept: list[Transaction] = []  # 남길 거래들
        found = False
        for tx in self.tx_repo.iter_all():
            if tx.id == tx_id:
                found = True
                continue  # 이 한 건만 kept 에 넣지 않는다 = 삭제
            kept.append(tx)
        if not found:
            # 없는 id 면 파일을 건드리지 않고 그대로 끝낸다.
            raise NotFoundError(
                f"존재하지 않는 id 입니다: {tx_id}",
                "'list' 로 유효한 id 를 확인하세요.",
            )
        self.tx_repo.rewrite(kept)

    # --------------------------- category -------------------------------- #
    def add_category(self, name: str) -> str:
        """카테고리를 추가한다."""
        name = (name or "").strip()
        if not name:
            raise ValidationError("카테고리명이 비어 있습니다.", "한 글자 이상 입력하세요.")
        if self.cat_store.exists(name):
            raise CategoryError(f"이미 존재하는 카테고리입니다: {name}", "다른 이름을 사용하세요.")
        self.cat_store.add(name)
        return name

    def list_categories(self) -> list[str]:
        """등록된 카테고리 목록."""
        return self.cat_store.list()

    def remove_category(self, name: str, replace_with: Optional[str] = None) -> int:
        """카테고리를 삭제한다. 사용 중이면 막거나 대체 카테고리를 요구한다.

        반환값: 다른 카테고리로 옮겨진 거래 건수.
        """
        name = (name or "").strip()
        if not self.cat_store.exists(name):
            raise NotFoundError(
                f"존재하지 않는 카테고리입니다: {name}", "'category list' 로 확인하세요."
            )
        # 이 카테고리를 쓰는 거래가 몇 건인지 센다.
        in_use = sum(1 for tx in self.tx_repo.iter_all() if tx.category == name)
        reassigned = 0
        if in_use:
            if not replace_with:
                # 대체 카테고리를 안 줬으면 삭제를 거부한다.
                raise CategoryError(
                    f"'{name}' 카테고리를 사용하는 거래가 {in_use}건 있어 삭제할 수 없습니다.",
                    "--replace-with <카테고리> 로 대체 카테고리를 지정하세요.",
                )
            replace_with = replace_with.strip()
            # 대체할 카테고리가 등록되어 있는지 확인.
            if not self.cat_store.exists(replace_with):
                raise CategoryError(
                    f"대체 카테고리가 존재하지 않습니다: {replace_with}",
                    "'category add' 로 먼저 등록하세요.",
                )
            # 해당 거래들의 카테고리를 전부 바꿔서 다시 쓴다.
            updated: list[Transaction] = []
            for tx in self.tx_repo.iter_all():
                if tx.category == name:
                    tx.category = replace_with
                    reassigned += 1
                updated.append(tx)
            self.tx_repo.rewrite(updated)
        # 거래 정리가 끝난 다음에 카테고리 삭제.
        remaining = [c for c in self.cat_store.list() if c != name]
        self.cat_store.replace_all(remaining)
        return reassigned

    # ---------------------------- budget --------------------------------- #
    def set_budget(self, month: str, amount: object) -> int:
        """한 달 예산을 저장한다."""
        month = validate_month(month)
        amount_int = validate_amount(amount)
        self.budget_store.set(month, amount_int)
        return amount_int

    # ------------------------- import / export --------------------------- #
    def import_csv(self, csv_path: str) -> tuple[int, int]:
        """CSV 파일을 읽어 거래로 추가한다.

        반환값: (성공 건수, 건너뛴 건수)
        """
        if not os.path.exists(csv_path):
            raise NotFoundError(f"파일을 찾을 수 없습니다: {csv_path}", "경로를 확인하세요.")
        imported = 0
        skipped = 0
        # id 번호 조회
        next_num = self.tx_repo.max_id_num() + 1
        buffer: list[Transaction] = []  # 성공한 거래를 모아 뒀다가 마지막에 한 번에 저장
        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            # DictReader 는 첫 줄을 헤더로 보고, 각 줄을 {"date": "...", ...} dict 로 준다.
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    type_ = validate_type(row.get("type", ""))
                    date = validate_date(row.get("date", ""))
                    amount = validate_amount(row.get("amount", ""))
                    category = (row.get("category") or "").strip()
                    if not self.cat_store.exists(category):
                        raise ValidationError("등록되지 않은 카테고리", "")
                    memo = (row.get("memo") or "").strip()
                    # "meal, fixed" 를 ["meal", "fixed"] 로 변환.
                    tags = [t.strip() for t in (row.get("tags") or "").split(",") if t.strip()]
                    buffer.append(
                        Transaction(
                            id=f"TX-{next_num:06d}",
                            type=type_,
                            date=date,
                            amount=amount,
                            category=category,
                            memo=memo,
                            tags=tags,
                        )
                    )
                    next_num += 1
                    imported += 1
                except (ValidationError, CategoryError):
                    skipped += 1
        # 모아 둔 것을 한 번에 저장
        self.tx_repo.append_many(buffer)
        return imported, skipped

    def export_csv(
        self,
        out_path: str,
        month: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> int:
        """조건에 맞는 거래를 CSV 파일로 내보낸다. 
        반환값: 내보낸 건수.
        """
        # 최소 한 가지 조건은 받도록 했다.
        if not month and not (date_from or date_to):
            raise ValidationError(
                "export 조건이 없습니다.",
                "--month YYYY-MM 또는 --from/--to 중 하나 이상을 지정하세요.",
            )
        if month:
            month = validate_month(month)
        if date_from:
            date_from = validate_date(date_from)
        if date_to:
            date_to = validate_date(date_to)

        def matches(tx: Transaction) -> bool:
            """search 의 matches 와 같은 방식 (조건에 안 맞으면 즉시 False)."""
            if month and tx.date[:7] != month:
                return False
            if date_from and tx.date < date_from:
                return False
            if date_to and tx.date > date_to:
                return False
            return True

        rows = [tx for tx in self.tx_repo.iter_all() if matches(tx)]
        rows.sort(key=lambda t: (t.date, t.id), reverse=True)

        with open(out_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_HEADER)  # 첫 줄은 항상 헤더
            for tx in rows:
                # 태그 리스트는 "meal,fixed" 처럼 한 칸에 합쳐서 넣는다.
                writer.writerow(
                    [tx.date, tx.type, tx.category, tx.amount, tx.memo, ",".join(tx.tags)]
                )
        return len(rows)

    # ---------------------- 반복 내역 (보너스) --------------------------- #
    def add_recurring(
        self,
        type_: str,
        day: object,
        category: str,
        amount: object,
        memo: str = "",
        tags: Optional[list[str]] = None,
    ) -> RecurringRule:
        """반복 내역을 등록한다.
        """
        type_ = validate_type(type_)
        day_int = validate_day(day)
        amount_int = validate_amount(amount)
        category = (category or "").strip()
        if not self.cat_store.exists(category):
            raise CategoryError(
                f"등록되지 않은 카테고리입니다: {category!r}",
                f"등록된 카테고리: {', '.join(self.cat_store.list()) or '(없음)'}",
            )
        rule = RecurringRule(
            id=self.recurring_store.next_id(),
            type=type_,
            day=day_int,
            category=category,
            amount=amount_int,
            memo=memo or "",
            tags=tags or [],
            # applied 는 일부러 비워 둔다. 아직 어떤 달에도 적용하지 않았으므로.
        )
        self.recurring_store.append(rule)
        return rule

    def list_recurring(self) -> list[RecurringRule]:
        """등록된 반복 내역 전체 목록."""
        return self.recurring_store.list()

    def remove_recurring(self, rule_id: str) -> None:
        """반복 내역을 삭제한다. (이미 만들어진 거래는 그대로 남는다)"""
        rules = self.recurring_store.list()
        # any(...) 는 "하나라도 조건에 맞으면 True".
        if not any(r.id == rule_id for r in rules):
            raise NotFoundError(
                f"존재하지 않는 반복 내역 id 입니다: {rule_id}",
                "'recurring list' 로 확인하세요.",
            )
        self.recurring_store.rewrite([r for r in rules if r.id != rule_id])

    def apply_recurring(self, month: str) -> tuple[list[Transaction], int]:
        """지정한 달에 반복 내역을 실제 거래로 생성한다.

        같은 달에 이미 처리한 반복 내역은 건너뛰어 중복 생성을 방지한다.
        또한 해당 월에 존재하지 않는 날짜는 그 달의 마지막 날로 보정한다.

        반환값: 생성된 거래 목록과 카테고리가 없어 건너뛴 반복 규칙 수
        """
        month = validate_month(month)
        # "2024-02" 에서 연도와 월을 잘라 숫자로 바꾼다.
        year, mon = int(month[:4]), int(month[5:7])
        # monthrange 는 (그 달 1일의 요일, 그 달의 총 일수)를 준다. [1] 로 일수만 꺼낸다.(윤년 계산)
        last_day = calendar.monthrange(year, mon)[1]
        rules = self.recurring_store.list()
        next_num = self.tx_repo.max_id_num() + 1
        generated: list[Transaction] = []
        skipped = 0
        changed = False  # 반복 내역 파일을 다시 써야 하는지 여부

        for rule in rules:
            if month in rule.applied:
                continue  # ★ 이미 이 달에 적용했다 -> 중복 생성하지 않는다
            if not self.cat_store.exists(rule.category):
                # 규칙을 만든 뒤에 그 카테고리가 삭제된 경우다. 건너뛰되 applied 에 적지 않는다.
                skipped += 1
                continue
            # min() 으로 그 달에 없는 날짜를 말일로 자른다. (31 vs 29 -> 29)
            day = min(rule.day, last_day)
            generated.append(
                Transaction(
                    id=f"TX-{next_num:06d}",
                    type=rule.type,
                    date=f"{month}-{day:02d}",
                    amount=rule.amount,
                    category=rule.category,
                    memo=rule.memo,
                    # list(...) 로 복사본을 넣는다. 그냥 rule.tags 를 넣으면
                    # 거래와 규칙이 같은 리스트를 공유해, 한쪽을 고치면 다른 쪽도 바뀐다.
                    tags=list(rule.tags),
                )
            )
            next_num += 1
            rule.applied.append(month)  # 해당 월은 처리 완료
            changed = True
        if generated:
            self.tx_repo.append_many(generated)
        if changed:
            # applied 기록이 바뀌었으므로 반복 내역 파일도 저장해야 한다.
            self.recurring_store.rewrite(rules)
        return generated, skipped

    # ------------------------- 백업 (보너스) ----------------------------- #
    def backup(self) -> list[str]:
        """모든 저장 파일을 타임스탬프가 붙은 사본으로 복사한다.
        """
        # strftime 은 시각을 원하는 모양의 문자열로 바꾼다.
        # "%Y%m%d_%H%M%S" -> "20240115_090000" (2024년 1월 15일 9시 정각)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        # 거래 파일이 있는 폴더 = 데이터 폴더. 그 안에 backups 폴더를 만든다.
        data_dir = os.path.dirname(os.path.abspath(self.tx_repo.path))
        backup_dir = os.path.join(data_dir, "backups")
        os.makedirs(backup_dir, exist_ok=True)
        created: list[str] = []
        for path in (
            self.tx_repo.path,
            self.cat_store.path,
            self.budget_store.path,
            self.recurring_store.path,
        ):
            # 아직 만들어지지 않은 파일은 건너뛴다(예: 예산을 한 번도 설정 안 한 경우).
            if os.path.exists(path):
                # 예: transactions.jsonl -> transactions.jsonl.20240115_090000.bak
                dst = os.path.join(backup_dir, f"{os.path.basename(path)}.{ts}.bak")
                # copy2 는 내용뿐 아니라 수정 시각 같은 정보까지 함께 복사한다.
                shutil.copy2(path, dst)
                created.append(dst)
        return created
