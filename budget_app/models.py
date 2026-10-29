"""데이터 모델 계층

1. 데이터의 정의 : 거래 한 건은 어떤 항목들로 이루어지는가?
   -> ``Transaction``, ``Category``, ``Budget``, ``RecurringRule`` 클래스
2. 올바른 값의 기준 정의 : 날짜는 어떤 형식이어야 하는가? 금액은?
   -> ``validate_...`` 로 시작하는 검증 함수들
"""

from __future__ import annotations

# dataclass : 값을 담는 클래스를 자동으로 만들어 주는 파이썬 기능 
# field     : dataclass 안에서 기본값을 특별하게 지정할 때 쓴다
from dataclasses import dataclass, field
from datetime import datetime
from .errors import ValidationError

# 거래 타입
# 튜플(소괄호)로 만든 이유: 리스트와 달리 나중에 실수로 바꿀 수 없기 때문.
VALID_TYPES: tuple[str, str] = ("income", "expense")


def _read_category_id(data: dict) -> str:
    """저장된 dict 에서 카테고리 외래키를 꺼낸다.

    지금 형식은 ``{"category_id": "CAT-000001"}`` 이지만,
    카테고리 이름을 그대로 넣던 예전 파일(``{"category": "food"}``)도
    읽을 수 있도록 두 가지를 모두 받아 준다. 예전 값(이름)을 실제 id 로
    바꾸는 일은 ``services.BudgetService.migrate_category_fk()`` 가 처리한다.
    """
    return str(data.get("category_id") or data.get("category") or "")


@dataclass
class Transaction:
    """거래 내역 한 건 (수입 또는 지출 하나).

    클래스 위에 붙은 ``@dataclass``은 아래처럼 '필드 이름 : 타입' 만 적어 두면, 파이썬이 ``__init__``(생성자), ``__repr__``(출력 형태), ``==`` 비교 등을 자동으로 만들어 준다.

    필드 설명
    ----
    id          : 유일 식별자 (예: ``TX-000012``)
    type        : ``income``(수입) 또는 ``expense``(지출)
    date        : ``YYYY-MM-DD`` 형식 문자열
    amount      : 양의 정수(원)
    category_id : 등록된 카테고리의 **PK**(예: ``CAT-000001``) — 외래키(FK)
    memo        : 메모(선택) — 안 쓰면 빈 문자열
    tags        : 태그 목록(선택) — 안 쓰면 빈 리스트

    카테고리를 '이름' 대신 'id' 로 가리키므로, 카테고리 이름을 바꿔도
    거래를 하나도 고치지 않아도 된다. 사람에게 보여 줄 이름은
    ``CategoryStore`` 에서 id 로 찾아온다.
    """

    # 기본값이 없는 필드 = 만들 때 반드시 넣어야 하는 값
    id: str
    type: str
    date: str
    amount: int
    category_id: str
    # 기본값이 있는 필드 = 안 넣으면 이 값이 들어감
    memo: str = ""
    # ``tags: list[str] = []`` 라고 쓰면
    # '리스트 하나'를 모든 Transaction 이 같이 써 버려서,
    # 한 거래에 태그를 추가하면 다른 거래에도 같이 붙는 황당한 버그가 생긴다.
    # 그래서 "필요할 때마다 새 리스트를 만들어라"라고 field(default_factory=...) 로 알려 준다.
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """이 객체를 딕셔너리(dict)로 바꾼다.

        파일에는 JSON 형태로 저장하기 위해 먼저 dict 형태로 바꾼다.
        (저장할 때의 흐름: Transaction -> dict -> JSON 문자열 -> 파일)
        """
        return {
            "id": self.id,
            "type": self.type,
            "date": self.date,
            "amount": self.amount,
            "category_id": self.category_id,
            "memo": self.memo,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Transaction":
        """dict 를 받아 Transaction 객체를 만들어 돌려준다.

        ``@classmethod`` 는 "객체가 아니라 클래스 자체에 딸린 함수"라는 뜻이다.
        그래서 객체를 먼저 만들지 않고 ``Transaction.from_dict(...)`` 처럼 바로 부를 수 있다.
        첫 번째 인자 ``cls`` 는 클래스 자신(= Transaction)을 가리킨다.

        (읽을 때의 흐름: 파일 -> JSON 문자열 -> dict -> Transaction)
        """
        return cls(
            id=str(data["id"]),
            type=str(data["type"]),
            date=str(data["date"]),
            amount=int(data["amount"]),
            category_id=_read_category_id(data),
            memo=str(data.get("memo", "") or ""),
            tags=list(data.get("tags", []) or []),
        )


@dataclass
class Category:
    """카테고리 한 건 (거래를 분류하는 이름표).

    필드 설명
    ----
    id   : 유일 식별자 (예: ``CAT-000001``)
    name : 카테고리 이름 (예: ``food``) — PK 는 아니지만 중복 등록은 막는다(유일 값).
    """

    id: str
    name: str

    def to_dict(self) -> dict:
        """저장을 위해 dict 로 변환."""
        return {"id": self.id, "name": self.name}

    @classmethod
    def from_dict(cls, data: dict) -> "Category":
        """파일에서 읽은 dict 로 객체 복원."""
        return cls(id=str(data["id"]), name=str(data["name"]))


@dataclass
class Budget:
    """한 달치 예산.

    ``month`` 는 ``YYYY-MM`` 형식(예: "2024-01")이고 ``amount`` 는 그 달의 예산 금액이다.
    """

    month: str  # YYYY-MM
    amount: int


@dataclass
class RecurringRule:
    """반복 내역 규칙 — 월급/월세처럼 매달 똑같이 생기는 항목의 틀.

    ``recurring apply --month 2024-03`` 을 실행하면 이 틀로 실제 거래를 찍어낸다.

    필드 설명
    ----
    id          : 유일 식별자 (예: ``R-000003``) — 거래(``TX-``)와 구분된다.
    type        : ``income``(수입) 또는 ``expense``(지출)
    day         : 매월 며칠에 생성할지 (1~31).
                  그 달에 그 날짜가 없으면(예: 2월 31일) 그 달의 마지막 날로 보정한다.
    category_id : 등록된 카테고리의 **PK**(예: ``CAT-000001``) — 거래와 마찬가지로 외래키(FK)
    amount      : 양의 정수(원)
    memo        : 메모(선택) — 안 쓰면 빈 문자열
    tags        : 태그 목록(선택) — 안 쓰면 빈 리스트
    applied     : 이미 거래를 만들어 둔 월들의 목록(예: ["2024-02", "2024-03"]).
                  같은 달에 실수로 두 번 실행해도 중복으로 만들지 않기 위한 기록이다.
    """

    id: str
    type: str
    day: int
    category_id: str
    amount: int
    memo: str = ""
    tags: list[str] = field(default_factory=list)
    applied: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """저장을 위해 dict 로 변환."""
        return {
            "id": self.id,
            "type": self.type,
            "day": self.day,
            "category_id": self.category_id,
            "amount": self.amount,
            "memo": self.memo,
            "tags": self.tags,
            "applied": self.applied,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RecurringRule":
        """파일에서 읽은 dict 로 객체 복원."""
        return cls(
            id=str(data["id"]),
            type=str(data["type"]),
            day=int(data["day"]),
            category_id=_read_category_id(data),
            amount=int(data["amount"]),
            memo=str(data.get("memo", "") or ""),
            tags=list(data.get("tags", []) or []),
            applied=list(data.get("applied", []) or []),
        )


# --------------------------------------------------------------------------- #
# 입력 검증 함수들
# --------------------------------------------------------------------------- #
def validate_date(value: str) -> str:
    """'2024-01-15' 같은 날짜 문자열인지 검사하고, 맞으면 그대로 돌려준다."""
    # (value or "") : value 가 None 이어도 오류 없이 빈 문자열로 처리
    value = (value or "").strip()
    try:
        # %Y=네 자리 연도, %m=두 자리 월, %d=두 자리 일
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ValidationError(
            f"날짜 형식이 올바르지 않습니다: {value!r}",
            "YYYY-MM-DD 형식으로 입력하세요. 예: 2024-01-15",
        )
    return value


def validate_month(value: str) -> str:
    """'2024-01' 같은 형식의 문자열인지 검사한다."""
    value = (value or "").strip()
    try:
        datetime.strptime(value, "%Y-%m")
    except ValueError:
        raise ValidationError(
            f"월 형식이 올바르지 않습니다: {value!r}",
            "YYYY-MM 형식으로 입력하세요. 예: 2024-01",
        )
    return value


def validate_type(value: str) -> str:
    """income / expense 둘 중 하나인지 검사한다."""
    value = (value or "").strip()
    if value not in VALID_TYPES:
        raise ValidationError(
            f"허용되지 않은 타입입니다: {value!r}",
            "income 또는 expense 중 하나여야 합니다.",
        )
    return value


def validate_amount(value: object) -> int:
    """금액이 '양의 정수'인지 검사하고, 정수로 바꿔서 돌려준다.

    받는 타입이 ``object``(무엇이든) 인 이유:
    대화형 입력에서는 문자열 "15000" 이 들어오고,
    명령 옵션에서는 이미 정수 15000 이 들어오기 때문이다.
    """
    try:
        amount = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValidationError(
            f"금액은 정수여야 합니다: {value!r}",
            "양의 정수를 입력하세요. 예: 15000",
        )
    # (지출/수입 구분은 type 필드가 하므로 금액 자체는 항상 양수다)
    if amount <= 0:
        raise ValidationError(
            f"금액은 양수여야 합니다: {amount}",
            "0보다 큰 정수를 입력하세요.",
        )
    return amount


def validate_day(value: object) -> int:
    """반복 내역의 '매월 며칠'(1~31)을 검증한다."""
    try:
        day = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValidationError(
            f"일(day)은 정수여야 합니다: {value!r}", "1~31 사이 정수를 입력하세요. 예: 25"
        )
    # 2월 31일'처럼 달마다 달라지는 문제는
    # 실제로 거래를 만들 때(services.apply_recurring) 말일로 보정한다.
    if not 1 <= day <= 31:
        raise ValidationError(
            f"일(day)은 1~31 범위여야 합니다: {day}", "예: 매월 25일이면 25"
        )
    return day
