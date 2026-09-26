"""직접 정의한 오류를 모아 둔 모듈.

예외 처리는 CLI 진입점의 `@handle_errors` 데코레이터에서 담당한다.
``[오류] 원인`` + ``[힌트] 해결 방법`` 만 보여 주고 0이 아닌 종료 코드를 돌려준다.
"""

# 파이썬이 타입 힌트를 '문자열처럼' 늦게 해석하게 해 주는 선언.
# 아직 정의되지 않은 클래스 이름도 타입 힌트에 쓸 수 있다.
from __future__ import annotations

class BudgetError(Exception):
    """이 프로그램의 모든 '예상 가능한 오류'의 부모 클래스.

    - message : 무엇이 잘못됐는지 (원인)
    - hint    : 그래서 어떻게 고치면 되는지 (해결 방법)
    """

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        
        self.message: str = message
        self.hint: str = hint

# 아래 세 클래스는 BudgetError 를 상속.
class ValidationError(BudgetError):
    """입력값 자체가 규칙에 맞지 않을 때. (날짜 형식, 금액이 0 이하, 잘못된 타입 등)"""

class NotFoundError(BudgetError):
    """찾으려는 대상이 없을 때. (없는 거래 id, 없는 카테고리, 없는 파일 등)"""

class CategoryError(BudgetError):
    """카테고리 관련 규칙을 어겼을 때. (미등록 / 이름 중복 / 사용 중인데 삭제 시도 등)"""
