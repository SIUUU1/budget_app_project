"""CLI 계층

CLI 는 Command Line Interface(명령줄 인터페이스)의 약자로,
마우스 없이 터미널에 명령을 쳐서 쓰는 방식을 말한다.

이 파일이 하는 일
  1. 사용자가 친 명령을 해석한다      (`list --limit 5` -> "목록을 5개 보여 달라")
  2. 부족한 정보는 되묻는다           (add 명령의 대화형 입력)
  3. 서비스에 일을 시킨다             (BudgetService 호출)
  4. 결과를 보기 좋게 출력한다        (표 정렬)
"""

from __future__ import annotations

# argparse : 명령줄 옵션을 해석해 주는 파이썬 표준 모듈.
# 직접 sys.argv 를 쪼개 분석할 때 사용함면 --help 나 오류 처리를 자동으로 해 준다.
import argparse
import os
from typing import Callable

from . import decorators
from .decorators import handle_errors, logged
from .errors import CategoryError, ValidationError
from .models import (
    VALID_TYPES,
    validate_amount,
    validate_date,
    validate_day,
    validate_type,
)
from .repository import (
    BudgetStore,
    CategoryStore,
    RecurringStore,
    TransactionRepository,
)
from .services import BudgetService

DEFAULT_DATA_DIR = "./data"


# --------------------------------------------------------------------------- #
# 조립
# --------------------------------------------------------------------------- #
def build_service(data_dir: str) -> BudgetService:
    """필요한 부품을 전부 만들어 조립한 BudgetService 를 돌려준다.

    저장소 4개를 만들고 서비스에 끼워 넣는 일을 여기 한곳에 모아 두면,
    나머지 코드는 완성된 service 하나만 받아서 쓰면 된다.
    """
    os.makedirs(data_dir, exist_ok=True)
    # os.path.join 은 폴더와 파일 이름을 운영체제에 맞게 이어 준다.
    tx_repo = TransactionRepository(os.path.join(data_dir, "transactions.jsonl"))
    cat_store = CategoryStore(os.path.join(data_dir, "categories.jsonl"))
    budget_store = BudgetStore(os.path.join(data_dir, "budgets.jsonl"))
    recurring_store = RecurringStore(os.path.join(data_dir, "recurring.jsonl"))
    # 처음 실행이면 기본 카테고리를 넣어 준다.
    # (카테고리가 하나도 없으면 거래를 아예 추가할 수 없기 때문)
    cat_store.ensure_defaults()
    service = BudgetService(tx_repo, cat_store, budget_store, recurring_store)
    # 카테고리를 이름으로 저장하던 예전 파일이면 id(FK) 기준으로 한 번 바꿔 준다.
    # (각 파일의 첫 줄만 확인하므로 평소에는 거의 비용이 없다)
    moved_tx, moved_rules = service.migrate_category_fk()
    if moved_tx or moved_rules:
        print(
            f"[안내] 예전 저장 형식을 category_id 기준으로 변환했습니다 "
            f"(거래 {moved_tx}건, 반복 규칙 {moved_rules}건)"
        )
    return service


# --------------------------------------------------------------------------- #
# 대화형 입력 헬퍼
# --------------------------------------------------------------------------- #
def _prompt(label: str) -> str:
    """질문을 보여 주고 한 줄을 입력받는다 (앞뒤 공백은 제거)."""
    return input(label).strip()


def _prompt_valid(label: str, validator: Callable[[str], object]) -> object:
    """**올바른 값을 넣을 때까지 계속 다시 묻는** 입력 함수.

    파이썬에서 함수는 숫자나 문자열처럼 변수에 담아 넘길 수 있는 값이다.
    그래서 이렇게 쓴다:
        _prompt_valid("날짜: ", validate_date)   <- 괄호 없이 이름만 넘긴다
    덕분에 '다시 묻기' 로직은 한 번만 만들어 두고
    날짜든 금액이든 타입이든 모든 검증에 재사용할 수 있다.

    타입 힌트 ``Callable[[str], object]`` 는
    "문자열 하나를 받아서 뭔가를 돌려주는 함수"라는 뜻.
    """
    while True:
        try:
            # 검증을 통과하면 다듬어진 값이 나오고, 그 즉시 return 으로 반복을 끝낸다.
            return validator(_prompt(label))
        except ValidationError as e:
            # 통과 못 하면 이유를 알려 주고 while 의 처음으로 돌아가 다시 묻는다.
            print(f"[오류] {e.message}")
            if e.hint:
                print(f"[힌트] {e.hint}")


# --------------------------------------------------------------------------- #
# 출력 포맷 (보너스: 외부 라이브러리 없이 컬럼 정렬)
# --------------------------------------------------------------------------- #
def _print_tx_table(txs: list, category_names: dict) -> None:
    """거래 목록을 칸이 맞는 표로 출력한다.

    거래에는 카테고리 id(FK)만 들어 있으므로, ``category_names``
    ({id: 이름} 사전)로 사람이 읽을 이름을 찾아 출력한다.

    ★ 출력 원리
      그냥 출력하면 글자 수가 달라 칸이 들쭉날쭉해진다.
          TX-000001 | 2024-01-05 | expense | food | 3000000
          TX-000002 | 2024-01-12 | income | transport | 20000
      그래서 먼저 **각 열에서 가장 긴 글자 수**를 구하고,
      모든 칸을 그 길이에 맞춰 공백으로 늘려 준다.
          ljust(n) : 왼쪽 정렬 (오른쪽을 공백으로 채움)  -> 글자에 어울린다
          rjust(n) : 오른쪽 정렬 (왼쪽을 공백으로 채움)  -> 숫자에 어울린다
      금액만 오른쪽 정렬하는 이유는, 그래야 자릿수가 세로로 맞아
      어느 쪽이 큰 금액인지 한눈에 보이기 때문이다.
    """
    if not txs:
        print("(거래 없음)")
        return
    # 모든 값을 문자열로 바꿔 둔다 (길이를 재고 붙이려면 문자열이어야 한다).
    rows = [
        [
            t.id,
            t.date,
            t.type,
            # 카테고리가 지워졌다면 id 를 그대로 보여 주어 이상을 알 수 있게 한다.
            category_names.get(t.category_id, t.category_id),
            str(t.amount),
            t.memo or "",
        ]
        for t in txs
    ]
    # 각 열(i번째 칸)에서 가장 긴 글자 수를 구한다.
    # 메모(5번 칸)는 길이를 재지 않는다. 맨 끝이라 맞출 필요가 없다.
    widths = [max(len(r[i]) for r in rows) for i in range(5)]
    for r in rows:
        cells = [
            r[0].ljust(widths[0]),  # id
            r[1].ljust(widths[1]),  # 날짜
            r[2].ljust(widths[2]),  # 타입
            r[3].ljust(widths[3]),  # 카테고리
            r[4].rjust(widths[4]),  # 금액 (숫자라서 우측 정렬)
            r[5],                   # 메모 (맨 끝이라 그대로)
        ]
        # " | ".join(리스트) : 리스트의 항목들을 " | " 로 이어 한 문자열로 만든다.
        print(" | ".join(cells))


# --------------------------------------------------------------------------- #
# 명령 핸들러
#
# 명령 하나당 함수 하나씩이며, 이름은 모두 cmd_ 로 시작한다.
# (service, args) 를 받아서 결과를 출력.
#   - service : 실제 일을 해 주는 BudgetService
#   - args    : 사용자가 준 옵션들이 담긴 꾸러미 (args.limit 처럼 꺼내 쓴다)
#
# 모든 함수에 @logged 가 붙어 있어 실행 로그와 소요 시간이 자동으로 남는다.
# --------------------------------------------------------------------------- #
@logged
def cmd_add(service: BudgetService, args: argparse.Namespace) -> None:
    """add — 거래 추가 (대화형: 하나씩 물어본다)."""
    print("거래를 추가합니다. (Ctrl+C 로 취소)")
    # 인풋값 타입 검증
    date = _prompt_valid("날짜(YYYY-MM-DD): ", validate_date)
    type_ = _prompt_valid("타입(income/expense): ", validate_type)
    # 카테고리 '기존에 등록되어 있는지' 확인 필요.
    while True:
        category = _prompt("카테고리: ")
        # 이름(food) 과 id(CAT-000001) 를 모두 받아 준다.
        if service.find_category(category) is not None:
            break
        print(f"[오류] 등록되지 않은 카테고리입니다: {category!r}")
        print(f"등록된 카테고리: {', '.join(service.cat_store.list())}")
        print("       'category add' 로 새 카테고리를 먼저 등록할 수 있습니다.")
    amount = _prompt_valid("금액(양수): ", validate_amount)
    memo = _prompt("메모(선택): ")
    tags_raw = _prompt("태그(쉼표로 구분, 없으면 엔터): ")
    # "meal, fixed" -> ["meal", "fixed"]
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
    tx = service.add_transaction(type_, date, category, amount, memo, tags)
    print(f"[저장 완료] id={tx.id}")


@logged
def cmd_list(service: BudgetService, args: argparse.Namespace) -> None:
    """list — 최신순 목록.

    list(...) 로 감싸는 이유: list_recent 는 제너레이터라 값을 하나씩만 준다.
    표를 그리려면 열 너비를 재야 하고, 그러려면 전체가 필요해서 여기서 리스트로 만든다.
    """
    _print_tx_table(list(service.list_recent(args.limit)), service.category_names())


@logged
def cmd_search(service: BudgetService, args: argparse.Namespace) -> None:
    """search — 조건 검색. 받은 옵션을 그대로 서비스에 넘기기만 한다."""
    results = service.search(
        date_from=args.date_from,
        date_to=args.date_to,
        category=args.category,
        type_=args.type,
        q=args.q,
        tag=args.tag,
    )
    _print_tx_table(results, service.category_names())


@logged
def cmd_summary(service: BudgetService, args: argparse.Namespace) -> None:
    """summary — 월별 요약."""
    s = service.summary(args.month, args.top)  # s 는 dict
    if not s["found"]:
        print(f"{args.month}: 데이터 없음")
        return
    print(f"총 수입: {s['total_income']}원")
    print(f"총 지출: {s['total_expense']}원")
    print(f"잔액: {s['balance']}원")
    budget = s["budget"]
    # 예산은 설정 안 했을 수 있다. None 이면 예산 관련 줄은 아예 출력하지 않는다.
    # (0 과 None 은 다르다: 0원 예산과 '예산 없음'은 의미가 다르므로 is not None 으로 비교)
    if budget is not None:
        # 예산이 0이면 나누기를 할 수 없다(0으로 나누면 오류).
        rate = (s["total_expense"] / budget * 100) if budget else 0.0
        print(f"예산: {budget}원 (사용률 {rate:.1f}%)")
        if s["total_expense"] > budget:
            over = s["total_expense"] - budget
            print(f"[경고] 예산을 초과했습니다! (초과액 {over}원)")
    if s["top"]:
        print(f"지출 TOP {len(s['top'])}")
        # enumerate(목록, 1) 은 (번호, 값) 을 함께 준다. 1부터 세라는 뜻으로 1을 넘겼다.
        for i, (cat, amt) in enumerate(s["top"], 1):
            print(f"{i}) {cat} {amt}원")


@logged
def cmd_budget(service: BudgetService, args: argparse.Namespace) -> None:
    """budget — 예산 설정(set) / 조회(list)."""
    if args.action == "set":
        # set 에는 --month 와 --amount 가 둘 다 있어야 한다.
        # argparse 로는 "set 일 때만 필수"를 표현하기 어려워서 여기서 직접 확인한다.
        if args.month is None or args.amount is None:
            raise ValidationError(
                "budget set 에는 --month 와 --amount 가 필요합니다.",
                "예: budget set --month 2024-01 --amount 500000",
            )
        amount = service.set_budget(args.month, args.amount)
        print(f"[저장 완료] {args.month} 예산 {amount}원")
    else:  # list
        budgets = service.budget_store.all()
        if not budgets:
            print("(예산 없음)")
        # sorted 로 월 순서대로 보여 준다.
        for m, a in sorted(budgets.items()):
            print(f"- {m}: {a}원")


@logged
def cmd_category(service: BudgetService, args: argparse.Namespace) -> None:
    """category — 카테고리 추가/조회/삭제."""
    if args.action == "add":
        # --name이 없으면 물어본다.
        name = args.name if args.name else _prompt("카테고리명: ")
        saved = service.add_category(name)
        print(f"[저장 완료] id={saved.id} category={saved.name}")
    elif args.action == "list":
        cats = service.list_categories()
        if not cats:
            print("(카테고리 없음)")
        for c in cats:
            # id 가 PK 이므로 이름과 함께 보여 준다.
            print(f"- {c.id} | {c.name}")
    else:  # remove
        if not args.name:
            raise ValidationError(
                "삭제할 카테고리명이 필요합니다.", "예: category remove --name food"
            )
        # 사용 중이면 여기서 CategoryError 가 나고, handle_errors 가 받아 처리한다.
        reassigned = service.remove_category(args.name, args.replace_with)
        msg = f"[삭제 완료] category={args.name}"
        if reassigned:
            # 거래를 옮겼다면 몇 건을 어디로 옮겼는지 알려 준다.
            # 사용자 몰래 데이터가 바뀌는 일이 없도록 하는 배려다.
            msg += f" (사용 중 거래 {reassigned}건을 '{args.replace_with}' 로 대체)"
        print(msg)


@logged
def cmd_update(service: BudgetService, args: argparse.Namespace) -> None:
    """update — 거래 수정."""
    # 옵션이 없으면 고칠 게 없다.
    # all(...) 은 "전부 조건에 맞으면 True" -> 전부 None 이면 True.
    if all(
        v is None
        for v in (args.date, args.type, args.category, args.amount, args.memo, args.tags)
    ):
        raise ValidationError(
            "수정할 필드를 하나 이상 지정하세요.",
            "예: update --id TX-000001 --amount 20000",
        )
    # tags : None 과 "" 를 구분.
    #   None -> 옵션을 안 줌 = 태그를 수정 안함.
    #   ""   -> --tags "" 로 줌 = 태그를 전부 비움.
    tags = None
    if args.tags is not None:
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    tx = service.update_transaction(
        args.id,
        date=args.date,
        type_=args.type,
        category=args.category,
        amount=args.amount,
        memo=args.memo,
        tags=tags,
    )
    print(f"[수정 완료] id={tx.id}")


@logged
def cmd_delete(service: BudgetService, args: argparse.Namespace) -> None:
    """delete — 거래 삭제."""
    service.delete_transaction(args.id)
    print(f"[삭제 완료] id={args.id}")


@logged
def cmd_import(service: BudgetService, args: argparse.Namespace) -> None:
    """import — CSV 가져오기. 성공/실패 건수를 함께 보여 준다."""
    imported, skipped = service.import_csv(args.src)
    print(f"[완료] imported={imported}, skipped={skipped}")


@logged
def cmd_export(service: BudgetService, args: argparse.Namespace) -> None:
    """export — CSV 내보내기."""
    n = service.export_csv(
        args.out, month=args.month, date_from=args.date_from, date_to=args.date_to
    )
    print(f"[완료] {args.out} ({n} records)")


@logged
def cmd_recurring(service: BudgetService, args: argparse.Namespace) -> None:
    """recurring — 반복 내역 등록/조회/삭제/적용 [보너스].
    """
    if args.action == "add":
        # 핵심 4개 옵션이 모두 있으면 옵션 모드(자동), 하나라도 빠지면 대화형.
        # 이렇게 해 두면 스크립트에서는 한 줄로 등록하고,
        # 사람은 옵션을 외우지 않아도 질문에 답하며 등록할 수 있다.
        option_mode = (
            args.type is not None
            and args.day is not None
            and args.category is not None
            and args.amount is not None
        )
        if option_mode:
            type_ = args.type
            day = args.day
            category = args.category.strip()
            if service.find_category(category) is None:
                raise CategoryError(
                    f"등록되지 않은 카테고리입니다: {category!r}",
                    f"등록된 카테고리: {', '.join(service.cat_store.list())}",
                )
            amount = args.amount
            # or "" : 옵션을 안 주면 None 인데, 뒤에서 .split() 을 하려면 문자열이어야 한다.
            memo = args.memo or ""
            tags_raw = args.tags or ""
        else:
            # 대화형 모드 — cmd_add 와 같은 방식으로 하나씩 물어본다.
            type_ = _prompt_valid("타입(income/expense): ", validate_type)
            day = _prompt_valid("반복일(1~31): ", validate_day)
            while True:
                category = _prompt("카테고리: ")
                if service.find_category(category) is not None:
                    break
                print(f"[오류] 등록되지 않은 카테고리입니다: {category!r}")
                print(f"등록된 카테고리: {', '.join(service.cat_store.list())}")
            amount = _prompt_valid("금액(양수): ", validate_amount)
            memo = _prompt("메모(선택): ")
            tags_raw = _prompt("태그(쉼표로 구분, 없으면 엔터): ")
        # input 값 받은 후
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
        rule = service.add_recurring(type_, day, category, amount, memo, tags)
        print(
            f"[저장 완료] id={rule.id} "
            f"(매월 {rule.day}일 · {rule.type} · {rule.amount}원 · "
            f"{service.category_label(rule.category_id)})"
        )
    elif args.action == "list":
        rules = service.list_recurring()
        if not rules:
            print("(반복 내역 없음)")
            return
        names = service.category_names()
        for r in rules:
            # 적용한 달이 있을 때만 그 부분을 덧붙인다(없으면 빈 문자열 = 아무것도 안 붙음).
            applied = f" · 적용월: {', '.join(r.applied)}" if r.applied else ""
            # 카테고리가 지워진 규칙은 apply 가 건너뛰므로 그 사실을 함께 보여 준다.
            category = names.get(r.category_id, f"{r.category_id}(삭제됨)")
            print(
                # {r.day:>2} 는 두 칸 폭으로 오른쪽 정렬. 5일과 25일의 줄을 맞춰 준다.
                f"{r.id} | 매월 {r.day:>2}일 | {r.type} | {category} | "
                f"{r.amount}원 | {r.memo}{applied}"
            )
    elif args.action == "remove":
        if not args.id:
            raise ValidationError(
                "삭제할 반복 내역 id 가 필요합니다.", "예: recurring remove --id R-000001"
            )
        service.remove_recurring(args.id)
        print(f"[삭제 완료] recurring={args.id}")
    else:  # apply
        if not args.month:
            raise ValidationError(
                "적용할 월이 필요합니다.", "예: recurring apply --month 2024-03"
            )
        generated, skipped = service.apply_recurring(args.month)
        print(f"[생성 완료] {args.month} 반복 내역 {len(generated)}건 생성")
        names = service.category_names()
        for tx in generated:
            category = names.get(tx.category_id, tx.category_id)
            print(f"- {tx.id} {tx.date} {tx.type} {category} {tx.amount}원")
        if skipped:
            print(f"[안내] 카테고리가 없어 건너뛴 규칙 {skipped}건 (카테고리 등록 후 다시 apply)")


@logged
def cmd_backup(service: BudgetService, args: argparse.Namespace) -> None:
    """backup — 데이터 파일 백업 [보너스]."""
    created = service.backup()
    if not created:
        print("[백업] 백업할 데이터 파일이 없습니다.")
        return
    print(f"[백업 완료] {len(created)}개 파일")
    for path in created:
        print(f"- {path}")


# --------------------------------------------------------------------------- #
# Parser 구성 — "어떤 명령과 옵션을 받을지"를 argparse 에 등록하는 부분
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    """명령줄 해석기(parser)를 만들어 돌려준다.

    여기에 등록해 두면 argparse 가 알아서
      - `--help` 도움말을 만들어 주고
      - 잘못된 옵션에 오류를 내 주고
      - `--limit 5` 의 5를 숫자로 바꿔 준다.
    """
    parser = argparse.ArgumentParser(
        prog="budget_app",  # 도움말에 표시될 프로그램 이름
        description="파일 기반 콘솔 가계부",
    )

    # ★ 공통 옵션 묶음 만들기
    # --data-dir 와 --verbose 는 모든 명령에서 쓸 수 있어야 한다.
    # 명령마다 두 줄씩 12번 복붙하는 대신, '부모 파서'를 하나 만들어 물려준다.
    # add_help=False 는 이 부모가 --help 를 중복해서 만들지 않음.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--data-dir", default=DEFAULT_DATA_DIR, help="데이터 저장 폴더 (기본: ./data)"
    )
    common.add_argument(
        # action="store_true" : 값 없이 --verbose 만 써도 True 가 된다.
        "--verbose", action="store_true", help="실행 로그를 표준 에러 스트림(stderr)에도 출력"
    )

    # 하위 명령(subcommand) 등록 시작.
    # git 의 `git commit`, `git push` 처럼 프로그램 하나가 여러 명령을 갖는 구조다.
    # required=True 라서 명령을 빼먹으면 argparse 가 알아서 오류를 낸다.
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    # 아래는 전부 같은 패턴이다:
    #   1) sub.add_parser(이름, parents=[common]) 로 명령 추가
    #   2) add_argument 로 그 명령만의 옵션 추가
    #   3) set_defaults(func=핸들러) 로 실행할 함수 연결
    # 3번 덕분에 run() 에서 if/elif 로 12번 분기하지 않고
    # args.func(...) 한 줄로 알맞은 함수를 부를 수 있다.

    p = sub.add_parser("add", parents=[common], help="거래 추가(대화형)")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("list", parents=[common], help="거래 목록(최신순, 스트리밍)")
    # type=int 를 쓰면 "5" 를 자동으로 숫자 5로 바꿔 준다(숫자가 아니면 오류).
    p.add_argument("--limit", type=int, default=20, help="출력 개수 (기본 20)")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("search", parents=[common], help="조건 검색(최신순)")
    # dest="date_from" : from 은 파이썬 예약어라 변수로 못 쓴다.
    # 그래서 사용자에게는 --from 으로 보여 주고, 코드에서는 args.date_from 으로 받는다.
    p.add_argument("--from", dest="date_from", help="시작일 YYYY-MM-DD")
    p.add_argument("--to", dest="date_to", help="종료일 YYYY-MM-DD")
    p.add_argument("--category")
    # choices 를 주면 목록에 없는 값은 argparse 가 미리 막아 준다.
    p.add_argument("--type", choices=list(VALID_TYPES))
    p.add_argument("--q", help="메모 키워드")
    p.add_argument("--tag")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("summary", parents=[common], help="월별 요약")
    # required=True : 이 옵션은 반드시 있어야 한다.
    p.add_argument("--month", required=True, help="YYYY-MM")
    p.add_argument("--top", type=int, default=5, help="카테고리별 지출 TOP N (기본 5)")
    p.set_defaults(func=cmd_summary)

    p = sub.add_parser("budget", parents=[common], help="예산 설정/조회")
    # 앞에 -- 가 없으면 '위치 인자'다. `budget set` 처럼 옵션 없이 바로 쓴다.
    p.add_argument("action", choices=["set", "list"])
    p.add_argument("--month", help="YYYY-MM")
    p.add_argument("--amount", type=int)
    p.set_defaults(func=cmd_budget)

    p = sub.add_parser("category", parents=[common], help="카테고리 관리")
    p.add_argument("action", choices=["add", "list", "remove"])
    p.add_argument("--name")
    # 옵션 이름에 - 가 있으면 파이썬 변수로 쓸 수 없어 dest 로 이름을 바꿔 준다.
    p.add_argument("--replace-with", dest="replace_with", help="사용 중 카테고리 대체용")
    p.set_defaults(func=cmd_category)

    p = sub.add_parser("update", parents=[common], help="거래 수정(옵션 기반)")
    p.add_argument("--id", required=True)
    p.add_argument("--date")
    p.add_argument("--type", choices=list(VALID_TYPES))
    p.add_argument("--category")
    p.add_argument("--amount", type=int)
    p.add_argument("--memo")
    p.add_argument("--tags", help="쉼표로 구분")
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("delete", parents=[common], help="거래 삭제")
    p.add_argument("--id", required=True)
    p.set_defaults(func=cmd_delete)

    p = sub.add_parser("import", parents=[common], help="CSV 가져오기")
    p.add_argument("--from", dest="src", required=True, help="가져올 CSV 경로")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("export", parents=[common], help="CSV 내보내기")
    p.add_argument("--out", required=True, help="저장할 CSV 경로")
    p.add_argument("--month", help="YYYY-MM")
    p.add_argument("--from", dest="date_from", help="YYYY-MM-DD")
    p.add_argument("--to", dest="date_to", help="YYYY-MM-DD")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser(
        "recurring", parents=[common], help="반복 내역(월급/월세 등) 등록·적용 [보너스]"
    )
    p.add_argument("action", choices=["add", "list", "remove", "apply"])
    # 동작마다 필요한 옵션이 달라서 일단 전부 선택으로 받아 두고,
    # "이 동작에는 이게 필요하다"는 확인은 cmd_recurring 안에서 한다.
    p.add_argument("--id", help="remove 대상 규칙 id")
    p.add_argument("--type", choices=list(VALID_TYPES))
    p.add_argument("--day", type=int, help="매월 며칠(1~31)")
    p.add_argument("--category")
    p.add_argument("--amount", type=int)
    p.add_argument("--memo")
    p.add_argument("--tags", help="쉼표로 구분")
    p.add_argument("--month", help="apply 대상 월 YYYY-MM")
    p.set_defaults(func=cmd_recurring)

    p = sub.add_parser(
        "backup", parents=[common], help="데이터 파일 백업(타임스탬프) [보너스]"
    )
    p.set_defaults(func=cmd_backup)

    return parser


@handle_errors
def run(argv: list[str] | None = None) -> int:
    """프로그램의 실제 시작 함수. 종료 코드(0 = 성공)를 돌려준다.

    ``@handle_errors`` 가 이 함수 전체를 감싸고 있어 아래 어느 줄에서 오류가 나든 메시지 + 종료 코드로 바뀐다.
    """
    parser = build_parser()
    # parse_args 가 사용자가 친 문자열들을 해석해 args 꾸러미로 만들어 준다.
    # 옵션이 잘못됐으면 여기서 argparse 가 직접 오류를 내고 프로그램을 끝낸다.
    args = parser.parse_args(argv)
    # getattr(객체, "이름", 기본값) : 그런 속성이 없어도 오류 없이 기본값을 준다.
    data_dir = getattr(args, "data_dir", DEFAULT_DATA_DIR)
    # 로그 설정
    decorators.configure(
        os.path.join(data_dir, "app.log"), verbose=getattr(args, "verbose", False)
    )
    service = build_service(data_dir)
    # ★ set_defaults(func=...) 로 미리 연결해 둔 함수를 부른다.
    args.func(service, args)
    return 0  # 여기까지 왔다면 성공
