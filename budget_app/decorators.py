"""데코레이터(decorator) 모듈 — 여러 기능이 공통으로 필요한 일을 한곳에 모은다.

데코레이터 : 함수를 감싸는 함수 

    @logged
    def cmd_list(service, args):
        ...

위 코드는 사실 ``cmd_list = logged(cmd_list)`` 와 완전히 같은 뜻이다.
그래서 이제 cmd_list 를 부르면, 실제로는 logged 가 만든 '포장된 함수'가 실행된다.

로그 남기기, 시간 재기, 오류 처리는 거의 모든 명령에 필요하지만
그 명령의 '본래 할 일'은 아니다(이런 걸 횡단 관심사라고 부른다).
이걸 함수마다 직접 쓰면 12개 명령에 똑같은 코드가 12번 복사된다.
데코레이터로 빼 두면 각 명령 함수는 자기 할 일만 적으면 된다.

- ``@logged``        : 실행 로그 + 걸린 시간(ms) 기록
- ``@handle_errors`` : 오류를 잡아서 친절한 메시지 + 종료 코드로 바꿈
"""

from __future__ import annotations

# functools : 함수를 다루는 도구 모음. 여기서는 wraps 를 사용.
import functools
import sys   # sys.stderr (오류 출력 통로) 를 쓰기 위해
import time
from datetime import datetime
from typing import Any, Callable  # 타입 힌트용: Callable = "함수 같은 것"

from .errors import BudgetError

# 모듈 전역 설정값
_log_path: str | None = None   # None = 아직 정해지지 않음
_verbose: bool = False         # True 면 화면에도 로그를 보여 준다

def configure(log_path: str | None, verbose: bool = False) -> None:
    """로그 파일 경로와 verbose 여부를 설정한다 (cli 진입점에서 딱 한 번 호출)."""
    # global 은 "함수 안에서 바깥 변수를 바꾸겠다"는 선언이다.
    # 이게 없으면 파이썬은 같은 이름의 새 지역 변수를 만들어 버려서,
    # 바깥 값은 그대로 남는다.
    global _log_path, _verbose
    _log_path = log_path
    _verbose = verbose


def _write_log(message: str) -> None:
    """로그 한 줄을 파일에 남긴다."""
    # isoformat(timespec='seconds') -> '2024-01-15T09:00:00' 처럼 초 단위까지만
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    if _verbose:
        # file=sys.stderr : 일반 결과(stdout)가 아니라 '오류/부가정보' 통로로 출력.
        print(line, file=sys.stderr)
    if _log_path:
        try:
            with open(_log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            # 로그 파일을 못 써도(권한 없음, 디스크 꽉 참 등)
            # 가계부 기능 자체는 계속 돌아가야 하므로 그냥 넘어간다.
            pass


def logged(func: Callable[..., Any]) -> Callable[..., Any]:
    """[데코레이터] 함수의 실행 시작/끝과 걸린 시간(ms)을 기록한다.

    구조를 보면 '함수를 받아서(func) 함수를 돌려주는(wrapper)' 모양이다.
    """

    # @functools.wraps(func) 를 붙이면 wrapper 가 원래 함수의 이름과 설명을 물려받는다.
    # 안 붙이면 모든 함수 이름이 'wrapper' 로 보여서 로그가 전부 똑같아진다.
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        # *args, **kwargs 는 "인자가 몇 개든, 이름이 뭐든 다 받아서 그대로 넘긴다"는 뜻.
        _write_log(f"START {func.__name__}")
        # perf_counter 는 시간 측정 전용 시계다.
        # (현재 시각용 time.time() 보다 정밀하고, 시스템 시계가 바뀌어도 영향받지 않는다)
        start = time.perf_counter()
        try:
            # 여기서 '원래 함수'를 실제로 실행하고, 그 결과를 그대로 돌려준다.
            return func(*args, **kwargs)
        finally:
            # 오류 자체는 잡지 않고 그대로 위로 흘려보낸다 -> handle_errors 가 처리
            elapsed_ms = (time.perf_counter() - start) * 1000  # 초 -> 밀리초
            _write_log(f"END   {func.__name__} ({elapsed_ms:.1f} ms)")

    return wrapper  # 포장된 새 함수를 돌려준다


def handle_errors(func: Callable[..., int]) -> Callable[..., int]:
    """[데코레이터] 오류를 '종료 코드'로 번역한다.

    종료 코드(exit code)
    - :class:`BudgetError`  -> ``[오류]``/``[힌트]`` 출력, 종료 코드 1
    - ``KeyboardInterrupt`` -> 종료 코드 130 (사용자가 Ctrl+C 로 중단)
    - 그 외 모든 예외       -> 스택트레이스 없이 요약만 출력, 종료 코드 2
    - 아무 문제 없음        -> 함수가 돌려준 값(보통 0)

    스택트레이스(stack trace): 프로그램에서 오류가 발생했을 때, 오류가 발생하기까지 어떤 함수들이 호출되었는지를 보여주는 기록
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> int:
        try:
            return func(*args, **kwargs)
        except BudgetError as e:
            # 우리가 예상한 오류 -> 원인과 힌트를 친절하게 보여 준다.
            print(f"[오류] {e.message}", file=sys.stderr)
            if e.hint:
                print(f"[힌트] {e.hint}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            # 사용자가 Ctrl+C 를 누른 경우. 오류가 아니라 '의도적 중단'이므로
            # 리눅스 관례에 따라 130 을 쓴다.
            print("\n[중단] 사용자가 실행을 취소했습니다.", file=sys.stderr)
            return 130
        except Exception as e:  # noqa: BLE001 - 최종 방어선
            # (# noqa 는 "여기서 모든 예외를 잡는 건 일부러 그런 것"이라고
            #  코드 검사 도구에게 알려 주는 주석이다)
            print(f"[오류] 예상치 못한 오류가 발생했습니다: {e}", file=sys.stderr)
            print("[힌트] 입력값과 데이터 파일 상태를 확인하세요.", file=sys.stderr)
            return 2

    return wrapper
