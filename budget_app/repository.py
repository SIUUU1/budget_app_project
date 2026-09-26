"""저장소(repository) 계층 — 파일을 실제로 읽고 쓰는 곳.

1) **JSONL 형식** : 파일 한 줄 = JSON 객체 하나.
       {"id": "TX-000001", "type": "income", ...}
       {"id": "TX-000002", "type": "expense", ...}

2) **제너레이터 스트리밍** : 파일 내용을 전부 메모리에 올리지 않고 한 줄씩 흘려보낸다.
   거래가 10만 건이어도 메모리에는 한 번에 한 건만 올라온다.

3) **원자적 교체** : 수정/삭제 때 원본을 직접 덮어쓰지 않고,
   임시 파일에 다 쓴 다음 한 번에 바꿔치기한다. 중간에 멈춰도 원본이 안 깨진다.
"""

from __future__ import annotations

import json
import os
import re
import tempfile  # 임시 파일 만들기
from typing import Iterable, Iterator, Optional

from .models import RecurringRule, Transaction

# 정규표현식(regular expression)
_ID_RE = re.compile(r"TX-(\d+)$")
_R_ID_RE = re.compile(r"R-(\d+)$")


# --------------------------------------------------------------------------- #
# 파일 입출력의 기본 기능을 담당하는 함수들
# --------------------------------------------------------------------------- #
def _iter_lines(path: str, encoding: str = "utf-8") -> Iterator[str]:
    """파일을 앞에서부터 한 줄씩 흘려보낸다(순방향 스트리밍).

    yield: 파일이 아무리 커도 메모리에는 한 줄만 올라온다.
      - 일반 함수 : 계산을 다 끝내고 결과를 한 번에 돌려준다.
      - 제너레이터: 값을 하나 만들 때마다 yield 로 내보내고 **그 자리에서 멈춰** 기다린다.
    """
    if not os.path.exists(path):
        return
    with open(path, "r", encoding=encoding) as f:
        for line in f:
            stripped = line.strip()
            if stripped:             # 빈 줄은 건너뛴다
                yield stripped


def _iter_lines_reversed(
    path: str, encoding: str = "utf-8", block_size: int = 8192
) -> Iterator[str]:
    """파일을 끝에서부터 한 줄씩 읽어오는 역방향 스트리밍 함수.

       파일 뒤쪽에 최신 거래가 저장되므로, 최근 거래만 필요한 경우
       파일 전체를 읽지 않고 끝에서부터 필요한 만큼만 읽어 성능을 높인다.

       파일을 8192바이트 단위의 블록으로 뒤에서부터 읽으며,
       블록 경계에서 잘린 줄은 buffer에 보관한 뒤 다음 블록과 합쳐
       완전한 한 줄로 만든 후 반환한다.
    """
    if not os.path.exists(path):
        return
    
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)  # 파일의 맨 끝으로 이동
        pos = f.tell()          # 현재 위치 = 파일 전체 크기(바이트)
        buffer = b""            # b"" 는 '빈 바이트열'. 잘린 조각을 모아 두는 곳.
        while pos > 0:          # 파일 맨 앞(0)에 도달할 때까지
            # 남은 양이 블록보다 적으면 남은 만큼만 읽는다
            read = min(block_size, pos)
            pos -= read         # 읽을 시작 위치를 그만큼 앞으로 이동
            f.seek(pos)         # 위치 이동
            # 읽은 블록 + 지난번에 남겨 둔 조각 = 이어 붙인 덩어리
            buffer = f.read(read) + buffer
            parts = buffer.split(b"\n")
            # parts[0] 은 이 덩어리의 맨 앞부분인데, 그 앞에 더 있을지 모름.
            buffer = parts[0]
            # parts[1:] 은 확실히 완성된 줄들.
            for raw in reversed(parts[1:]):
                stripped = raw.strip()
                if stripped:
                    # 바이트를 문자열로 바꿔서 내보낸다 (b'{"id"...}' -> '{"id"...}')
                    yield stripped.decode(encoding)

        # buffer 에 남은 것 출력.
        stripped = buffer.strip()
        if stripped:
            yield stripped.decode(encoding)


def _atomic_write_lines(path: str, lines: Iterable[str], encoding: str = "utf-8") -> None:
    """파일을 안전하게 덮어쓰는 함수 (원자적 쓰기).

       임시 파일에 새 내용을 모두 저장한 후 os.replace()로
       원본 파일과 교체하여, 저장 중 오류가 발생해도
       파일이 중간 상태로 남지 않도록 한다.
    """
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)  # exist_ok=True : 이미 있어도 오류 안 냄
    # mkstemp 는 이름이 겹치지 않는 임시 파일을 만들고
    # (파일 번호, 경로) 두 개를 돌려준다.
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp_", suffix=".jsonl")
    try:
        # fdopen 은 위에서 받은 파일 번호(fd)를 파일 객체로 바꿔 준다.
        with os.fdopen(fd, "w", encoding=encoding) as f:
            for line in lines:
                f.write(line + "\n")
        os.replace(tmp, path)  # ★ 여기가 원자적 교체 — 성공하면 임시 파일은 사라진다
    except BaseException:
        # BaseException 은 Ctrl+C 같은 것까지 포함해 '모든' 예외를 잡는다.
        # 실패하면 임시 파일 제거
        if os.path.exists(tmp):
            os.remove(tmp)
        raise #handle_errors에서 처리


# --------------------------------------------------------------------------- #
# 거래 저장소
# --------------------------------------------------------------------------- #
class TransactionRepository:
    """transactions.jsonl 을 다루는 저장소."""

    def __init__(self, path: str) -> None:
        self.path = path

    def iter_all(self) -> Iterator[Transaction]:
        """순방향 스트리밍 — 전체 목록용(검색/요약/내보내기).
        """
        for line in _iter_lines(self.path):
            # 한 줄(JSON 문자열) -> dict -> Transaction 객체 순서로 변환
            yield Transaction.from_dict(json.loads(line))

    def iter_recent(self) -> Iterator[Transaction]:
        """역방향 스트리밍 — 최신순 목록용. --limit 와 합쳐 조기 종료할 수 있다."""
        for line in _iter_lines_reversed(self.path):
            yield Transaction.from_dict(json.loads(line))

    def append(self, tx: Transaction) -> None:
        """거래 한 건을 파일 맨 뒤에 덧붙인다.
        """
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(tx.to_dict(), ensure_ascii=False) + "\n")

    def append_many(self, txs: Iterable[Transaction]) -> None:
        """여러 건을 한 번에 덧붙인다
        """
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            for tx in txs:
                f.write(json.dumps(tx.to_dict(), ensure_ascii=False) + "\n")

    def rewrite(self, txs: Iterable[Transaction]) -> None:
        """파일 전체를 새로 쓴다 (update/delete 후에 사용, 원자적 교체).

           JSONL은 중간의 한 줄을 수정하거나 삭제하려면 뒤쪽 데이터를 함께 처리해야 한다.
           따라서 수정/삭제는 일반적으로 전체 파일을 다시 쓰는 방식으로 처리한다.
        """
        _atomic_write_lines(
            self.path,
            # 소괄호로 쓴 이것은 '제너레이터 표현식'이다.
            # 소괄호 ( ) 는 필요할 때 한 줄씩 만들어 낸다.
            (json.dumps(t.to_dict(), ensure_ascii=False) for t in txs),
        )

    def max_id_num(self) -> int:
        """지금까지 쓰인 id 중 가장 큰 번호를 찾는다 (예: TX-000012 -> 12).
        """
        max_num = 0
        for tx in self.iter_all():
            m = _ID_RE.match(tx.id)  # 패턴에 맞으면 결과 객체, 아니면 None
            if m:
                # group(1) = 정규식에서 괄호로 묶었던 첫 부분 = 숫자 부분
                max_num = max(max_num, int(m.group(1)))
        return max_num

    def next_id(self) -> str:
        """다음에 쓸 새 id 를 만든다.
        """
        return f"TX-{self.max_id_num() + 1:06d}"


# --------------------------------------------------------------------------- #
# 카테고리 저장소
# --------------------------------------------------------------------------- #
class CategoryStore:
    """categories.jsonl 을 다루는 저장소."""

    # 기본 카테고리 목록
    DEFAULTS: list[str] = ["food", "transport", "rent", "salary", "etc"]

    def __init__(self, path: str) -> None:
        self.path = path

    def list(self) -> list[str]:
        """카테고리 이름을 리스트로 반환.
        """
        return [json.loads(line)["name"] for line in _iter_lines(self.path)]

    def exists(self, name: str) -> bool:
        """해당 카테고리명이 등록되어 있는지 확인. (거래를 추가하기 전에 꼭 확인한다)"""
        return name in self.list()

    def add(self, name: str) -> None:
        """카테고리 하나를 파일에 추가"""
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"name": name}, ensure_ascii=False) + "\n")

    def replace_all(self, names: list[str]) -> None:
        """카테고리 목록 전체를 새 목록으로 교체한다 (삭제할 때 사용)."""
        _atomic_write_lines(
            self.path,
            (json.dumps({"name": n}, ensure_ascii=False) for n in names),
        )

    def ensure_defaults(self) -> None:
        """파일이 없거나 비어 있으면 기본 카테고리를 채워 넣는다.

        프로그램을 처음 켰을 때 카테고리가 하나도 없으면
        거래를 단 한 건도 추가할 수 없다(카테고리는 필수).
        """
        if not os.path.exists(self.path) or not self.list():
            self.replace_all(self.DEFAULTS)


# --------------------------------------------------------------------------- #
# 예산 저장소
# --------------------------------------------------------------------------- #
class BudgetStore:
    """budgets.jsonl 을 다루는 저장소 (월 -> 금액)."""

    def __init__(self, path: str) -> None:
        self.path = path

    def all(self) -> dict[str, int]:
        """전체 예산을 {"2024-01": 500000, ...} 모양의 dict 로 반환.
        """
        result: dict[str, int] = {}
        for line in _iter_lines(self.path):
            data = json.loads(line)
            # 같은 달이 여러개 있더라도 가장 마지막에 저장한 값이 출력.
            result[data["month"]] = int(data["amount"])
        return result

    def get(self, month: str) -> Optional[int]:
        """특정 달의 예산을 돌려준다. 설정한 적이 없으면 None.

        Optional[int] : int 이거나 None 일 수 있다는 뜻의 타입 힌트다.
        """
        return self.all().get(month)

    def set(self, month: str, amount: int) -> None:
        """특정 달의 예산을 저장한다 (이미 있으면 덮어쓴다)."""
        data = self.all()      # 1. 기존 내용을 전부 읽어서
        data[month] = amount   # 2. 해당 달만 바꾸고
        _atomic_write_lines(   # 3. 전체를 다시 쓴다
            self.path,
            (
                json.dumps({"month": m, "amount": a}, ensure_ascii=False)
                # sorted 로 월 순서대로 정렬해 둔다.
                for m, a in sorted(data.items())
            ),
        )


# --------------------------------------------------------------------------- #
# 반복 내역 저장소 (보너스)
# --------------------------------------------------------------------------- #
class RecurringStore:
    """recurring.jsonl 을 다루는 저장소
    """

    def __init__(self, path: str) -> None:
        self.path = path

    def iter_all(self) -> Iterator[RecurringRule]:
        """반복 내역을 한 건씩 흘려보낸다."""
        for line in _iter_lines(self.path):
            yield RecurringRule.from_dict(json.loads(line))

    def list(self) -> list[RecurringRule]:
        """반복 내역 전체를 리스트로 돌려준다.
        """
        return list(self.iter_all())

    def append(self, rule: RecurringRule) -> None:
        """반복 내역 하나를 뒤에 덧붙인다."""
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rule.to_dict(), ensure_ascii=False) + "\n")

    def rewrite(self, rules: Iterable[RecurringRule]) -> None:
        """반복 내역 파일 전체를 다시 쓴다 (삭제하거나 applied 기록을 갱신할 때)."""
        _atomic_write_lines(
            self.path,
            (json.dumps(r.to_dict(), ensure_ascii=False) for r in rules),
        )

    def max_id_num(self) -> int:
        """지금까지 쓰인 규칙 id 중 가장 큰 번호 (R-000003 -> 3)."""
        max_num = 0
        for rule in self.iter_all():
            m = _R_ID_RE.match(rule.id)
            if m:
                max_num = max(max_num, int(m.group(1)))
        return max_num

    def next_id(self) -> str:
        """다음에 쓸 규칙 id (거래는 TX-, 규칙은 R- 로 구분한다)."""
        return f"R-{self.max_id_num() + 1:06d}"
