"""budget_app: 파일 기반 콘솔 가계부.

계층(모듈) 구조
---------------
- models      : 데이터 구조(dataclass) + 입력 검증 함수
- repository  : 파일 I/O(JSONL) + 제너레이터 스트리밍 + 원자적 교체
- services    : 도메인 로직(BudgetService)
- cli         : 인자 파싱 / 대화형 입력 / 출력 포맷 / 명령 디스패치
- decorators  : 공통 관심사(실행 로그 · 시간 측정 · 예외 처리) 분리
- errors      : 도메인 예외 정의

각 계층은 아래 방향으로만 의존한다:
    cli -> services -> repository -> models
    (decorators, errors 는 공통 지원 모듈)

★ '한 방향으로만 의존한다'가 왜 중요할까?
  cli 는 services 를 부르지만, services 는 cli 를 부르지 않는다.
  화살표가 한쪽으로만 흐르면 '서로가 서로를 부르는' 꼬인 구조가 생기지 않는다.
  그래서 아래쪽(models, repository)만 따로 떼어 테스트할 수 있고,
  화면 출력 방식을 바꿔도 저장 로직은 전혀 건드릴 필요가 없다.
"""

# 패키지 버전. 관례적으로 __version__ 이라는 이름을 쓴다.
__version__ = "1.0.0"
