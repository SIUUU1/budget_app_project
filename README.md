# budget_app — 파일 기반 콘솔 가계부

수입/지출 내역을 추가·조회·검색·수정·삭제하고, 월별 요약과 예산 초과 경고,
카테고리 관리, CSV 가져오기/내보내기, **백업**, **반복 내역 자동 생성**까지 제공하는
콘솔 프로그램입니다. 데이터는 프로그램 종료 후에도 유지되도록 **JSONL 파일**로 영구 저장합니다.

- 개발 환경: **Python 3.10 이상** (검증: 3.12)
- 의존성: **표준 라이브러리만 사용** (별도 `pip install` 불필요)

---

## 1. 실행 방법

프로젝트 루트(이 README가 있는 폴더)에서 실행합니다.

```bash
python -m budget_app <command> [options]
```

모든 명령은 `--help` 로 사용법을 볼 수 있습니다.

```bash
python -m budget_app --help
python -m budget_app add --help
python -m budget_app recurring --help
```

- 옵션 표기는 리눅스 표준 `--` 로 통일합니다. (예: `--limit`, `--from`, `--to`, `--month`)
- 정상 종료 시 exit code `0`, 오류 종료 시 `0`이 아닌 값을 반환합니다.
- 공통 옵션
  - `--data-dir <경로>` : 저장 폴더 변경 (기본 `./data`)
  - `--verbose` : 실행 로그/시간을 stderr 에도 출력

### 명령 한눈에 보기

| 명령 | 설명 | 입력 방식 |
| --- | --- | --- |
| `add` | 거래 추가 | 대화형 |
| `list` | 거래 목록(최신순) | 옵션 |
| `search` | 조건 검색 | 옵션 |
| `summary` | 월별 요약(+예산) | 옵션 |
| `budget` | 예산 설정/조회 | 옵션 |
| `category` | 카테고리 관리 | 옵션/대화형 |
| `update` | 거래 수정 | 옵션 |
| `delete` | 거래 삭제 | 옵션 |
| `import` / `export` | CSV 가져오기/내보내기 | 옵션 |
| `recurring` | 반복 내역 등록·적용 **[보너스]** | 옵션/대화형 |
| `backup` | 데이터 백업 **[보너스]** | 옵션 없음 |

---

## 2. 저장 파일 위치 / 형식

기본 저장 폴더는 `./data` 이며, 저장 포맷은 **JSONL**(한 줄에 JSON 객체 1개)로 통일했습니다.
데이터는 아래처럼 **여러 파일로 분리**하여 영구 저장합니다.

| 파일 | 내용 | 한 줄 예시 |
| --- | --- | --- |
| `transactions.jsonl` | 거래 내역 | `{"id":"TX-000001","type":"expense","date":"2024-01-15","amount":15000,"category_id":"CAT-000001","memo":"점심","tags":["meal"]}` |
| `categories.jsonl` | 카테고리 | `{"id":"CAT-000001","name":"food"}` |
| `budgets.jsonl` | 월 예산 | `{"month":"2024-01","amount":500000}` |
| `recurring.jsonl` | 반복 내역 규칙 **[보너스]** | `{"id":"R-000001","type":"income","day":25,"category_id":"CAT-000004","amount":3000000,"memo":"월급","tags":[],"applied":["2024-03"]}` |

그 외:
- `data/backups/` : `backup` 명령으로 만든 타임스탬프 백업 파일 폴더 **[보너스]**
- `data/app.log` : 실행 로그(어떤 명령이 언제, 몇 ms 걸렸는지)

기타 규칙:
- 인코딩은 UTF-8 입니다.
- **초기 실행**(저장 파일이 없을 때): 폴더/파일을 자동 생성하고, 카테고리가 비어 있으면
  **기본 카테고리를 자동 생성**합니다: `food, transport, rent, salary, etc`
- `update` / `delete` / 카테고리 대체는 **임시 파일에 쓰고 `os.replace` 로 원자적 교체**하여
  중간에 실패해도 원본 파일이 깨지지 않도록 처리합니다.
- **예전 형식 자동 변환**: 카테고리를 이름으로 저장했던 파일(`"category":"food"`)을 발견하면
  첫 실행 때 `category_id` 기준으로 한 번 바꾸고 `[안내]` 를 출력합니다.
  (각 파일의 **첫 줄만** 확인하므로 평소에는 비용이 거의 없습니다)

---

## 3. 데이터 모델 (ERD)

네 종류의 데이터를 각각 별도 JSONL 파일에 저장합니다.

```text
           ┌──────────────────────┐
           │       CATEGORY       │
           │  id (PK)             │
           │  name (UK)           │
           └──────────┬───────────┘
                      │ 1
          ┌───────────┴────────────┐
          │ N                      │ N
┌─────────┴──────────┐   ┌─────────┴─────────────────┐
│    TRANSACTION     │   │      RECURRING_RULE       │
│  id (PK)           │ N │  id (PK)                  │
│  type              │◀──┤  type                     │
│  date              │ 1 │  day (1~31)               │
│  amount            │   │  category_id (FK)         │
│  category_id (FK)  │   │  amount                   │
│  memo              │   │  memo / tags              │
│  tags              │   │  applied [YYYY-MM, ...]   │
└─────────┬──────────┘   └───────────────────────────┘
          │ N
          │  date[:7] == month
          │ 1
┌─────────┴──────────┐
│       BUDGET       │
│  month (PK)        │
│  amount            │
└────────────────────┘
```

### 관계 설명

| 관계 | 의미 | 비고 |
| --- | --- | --- |
| `CATEGORY (1) ─ (N) TRANSACTION` | 거래는 반드시 **등록된 카테고리** 하나를 `category_id` 로 가리킨다 | `add`/`update`/`import` 시 `require_category()` 로 검사. 사용 중인 카테고리는 삭제를 막고 `--replace-with` 로만 정리(이때 거래의 `category_id` 를 대체 카테고리 id 로 바꿔 다시 씀) |
| `CATEGORY (1) ─ (N) RECURRING_RULE` | 반복 규칙도 등록된 카테고리를 `category_id` 로 가리킨다 | 등록 시 검사. 나중에 카테고리가 사라지면 `apply` 가 그 규칙을 **건너뛰고 안내**(적용 표시하지 않음), `recurring list` 는 `CAT-000003(삭제됨)` 으로 보여 줌 |
| `RECURRING_RULE (1) ─ (N) TRANSACTION` | `apply --month` 한 번에 규칙 하나가 거래 한 건을 낳는다 | 생성된 거래는 일반 거래와 동일. 규칙의 `applied` 에 그 월을 기록해 **재실행해도 중복 생성 안 함** |
| `BUDGET (1) ─ (N) TRANSACTION` | 예산과 거래는 `month` ↔ `date[:7]` 로 느슨하게 연결된다 | `summary` 가 그 달 지출 합계와 예산을 비교해 사용률·초과 경고를 계산 |

### 식별자(PK) 규칙

- `TRANSACTION.id` : `TX-` + 6자리 (`TX-000001`). 기존 파일에서 최대 번호를 스캔해 +1.
- `RECURRING_RULE.id` : `R-` + 6자리 (`R-000001`). 같은 방식.
- `CATEGORY.id` : `CAT-` + 6자리 (`CAT-000001`). 같은 방식이며 **PK 는 이 `id` 하나뿐**입니다.
- `CATEGORY.name` 은 PK 가 아니지만 사람이 직접 입력하는 이름이라 **중복 등록을 막습니다**(유일 값, UK).
- `BUDGET.month` 는 값 자체가 키이므로 중복 등록을 막습니다.

**외래키(FK)** : `TRANSACTION.category_id` / `RECURRING_RULE.category_id` 는 `CATEGORY.id` 를 가리킵니다.
이름이 아니라 id 로 가리키므로 **카테고리 이름이 바뀌어도 거래를 고칠 필요가 없습니다.**

- 명령에서는 `--category food` 처럼 **이름**으로 쓰고, `--category CAT-000001` 처럼 **id** 로도 쓸 수 있습니다
  (`BudgetService.find_category()` 가 id -> 이름 순으로 찾습니다).
- 화면과 CSV 에는 다시 **이름**으로 보여 줍니다(`category_names()` 로 `{id: 이름}` 을 한 번만 만들어 사용).
- 등록되지 않은 카테고리로 `search` 하면 오류 대신 결과 없음으로 처리합니다.

### 모델 ↔ 코드 대응

| 엔터티 | dataclass ([models.py](budget_app/models.py)) | 저장소 ([repository.py](budget_app/repository.py)) | 파일 |
| --- | --- | --- | --- |
| TRANSACTION | `Transaction` | `TransactionRepository` | `transactions.jsonl` |
| CATEGORY | `Category` | `CategoryStore` | `categories.jsonl` |
| BUDGET | `Budget` (구조 정의용, 저장소는 `month → amount` dict 로 다룸) | `BudgetStore` | `budgets.jsonl` |
| RECURRING_RULE | `RecurringRule` | `RecurringStore` | `recurring.jsonl` |

---

## 4. 주요 명령 예시

### add — 거래 추가(대화형)

```text
$ python -m budget_app add
날짜(YYYY-MM-DD): 2024-01-15
타입(income/expense): expense
카테고리: food
금액(양수): 15000
메모(선택): 점심
태그(쉼표로 구분, 없으면 엔터): meal
[저장 완료] id=TX-000001
```

### list — 거래 목록(최신순, 스트리밍)

```text
$ python -m budget_app list --limit 3
TX-000005 | 2024-01-22 | expense | food      |  30000 | 저녁
TX-000004 | 2024-01-20 | expense | rent      | 150000 | 월세
TX-000003 | 2024-01-12 | expense | transport |  20000 |
```

### search — 조건 검색(최신순)

```bash
python -m budget_app search --from 2024-01-01 --to 2024-01-31 \
    --category food --type expense --q 점심 --tag meal
```

옵션: `--from`, `--to`, `--category`, `--type`, `--q`(메모 키워드), `--tag`

### summary — 월별 요약(+ 예산)

```text
$ python -m budget_app summary --month 2024-01 --top 3
총 수입: 3000000원
총 지출: 215000원
잔액: 2785000원
예산: 500000원 (사용률 43.0%)
지출 TOP 3
1) rent 150000원
2) food 45000원
3) transport 20000원
```

예산을 초과하면 `[경고] 예산을 초과했습니다! (초과액 ...원)` 문구가 함께 나옵니다.
데이터가 없는 달은 `데이터 없음` 을 출력합니다.

### budget / category / update / delete

```bash
python -m budget_app budget set --month 2024-01 --amount 500000
python -m budget_app budget list

python -m budget_app category add            # 대화형(카테고리명 입력)
python -m budget_app category list
python -m budget_app category remove --name food --replace-with etc

python -m budget_app update --id TX-000001 --amount 18000 --memo 수정
python -m budget_app delete --id TX-000001
```

`category list` 는 `- CAT-000001 | food` 처럼 **PK(`id`)와 이름을 함께** 보여 줍니다.
카테고리 삭제 시 그 카테고리를 쓰는 거래가 있으면 **삭제를 막고, `--replace-with` 로 대체**를 요구합니다.

### import / export — CSV

```text
$ python -m budget_app export --out export.csv --month 2024-01
[완료] export.csv (12 records)

$ python -m budget_app import --from import.csv
[완료] imported=5, skipped=0
```

`export` 는 `--month` 또는 `--from`/`--to` 중 **하나 이상**을 필수로 받습니다.

### recurring — 반복 내역(월급/월세 등) **[보너스]**

```text
$ python -m budget_app recurring add --type income --day 25 --category salary --amount 3000000 --memo 월급
[저장 완료] id=R-000001 (매월 25일 · income · 3000000원 · salary)

$ python -m budget_app recurring list
R-000001 | 매월 25일 | income | salary | 3000000원 | 월급

$ python -m budget_app recurring apply --month 2024-03
[생성 완료] 2024-03 반복 내역 1건 생성
- TX-000001 2024-03-25 income salary 3000000원

$ python -m budget_app recurring apply --month 2024-03   # 같은 달 재실행 시
[생성 완료] 2024-03 반복 내역 0건 생성                    # 중복 생성하지 않음
```

- `add` 는 옵션(위 예시) 또는 대화형 모두 가능합니다.
- `apply --month` 로 해당 월의 거래를 자동 생성합니다. 같은 달에 다시 실행해도 **중복 생성되지 않습니다.**
- 해당 월에 없는 날짜(예: 2월 31일)는 **그 달의 마지막 날**로 보정합니다.
- 삭제: `recurring remove --id R-000001`

### backup — 데이터 백업 **[보너스]**

```text
$ python -m budget_app backup
[백업 완료] 4개 파일
- ./data/backups/transactions.jsonl.20240115_090000.bak
- ./data/backups/categories.jsonl.20240115_090000.bak
- ./data/backups/budgets.jsonl.20240115_090000.bak
- ./data/backups/recurring.jsonl.20240115_090000.bak
```

모든 저장 파일을 `data/backups/` 폴더에 **타임스탬프가 붙은 사본**으로 복사합니다.

---

## 5. import/export CSV 스키마

- 인코딩: UTF-8, **헤더 포함**
- 컬럼 순서: `date, type, category, amount, memo, tags`

| column | required | 설명 |
| --- | --- | --- |
| `date` | Y | `YYYY-MM-DD` |
| `type` | Y | `income` / `expense` |
| `category` | Y | 등록된 카테고리 **이름**(또는 id). 저장할 때 `category_id` 로 변환되고, export 시 다시 이름으로 적습니다 |
| `amount` | Y | 양수 정수 |
| `memo` | N | 문자열 |
| `tags` | N | 쉼표(`,`) 구분 문자열 |

예시:

```csv
date,type,category,amount,memo,tags
2024-01-15,expense,food,15000,점심,meal
2024-01-14,income,salary,3000000,,
```

---

## 6. 설계 / 구조

한 파일에 몰지 않고 **계층(모듈)별로 책임을 분리**했습니다.

```
budget_app_project/
├── README.md           이 문서
├── .gitignore          실행 산출물(data/, *.jsonl, 백업, 로그 등) 제외
├── demo.sh             전체 기능 시연 스크립트 (8번 참고)
├── data/               저장 폴더 (실행 시 자동 생성, git 추적 제외)
└── budget_app/
    ├── __init__.py     패키지 설명
    ├── __main__.py     진입점 (python -m budget_app) / 종료 코드 반환
    ├── models.py       데이터 구조(dataclass) + 입력 검증 함수 (타입 힌트)
    ├── repository.py   파일 I/O(JSONL) + 제너레이터 스트리밍 + 원자적 교체
    ├── services.py     도메인 로직 (BudgetService)
    ├── cli.py          인자 파싱 / 대화형 입력 / 출력 포맷 / 디스패치
    ├── decorators.py   공통 관심사(실행 로그·시간 측정·예외 처리)
    └── errors.py       도메인 예외(원인 + 해결 힌트)
```

의존 방향: `cli → services → repository → models` (decorators, errors 는 공통 지원)

**필수 요구사항**: 제너레이터 스트리밍(list는 파일 끝에서부터 읽어 `--limit` 도달 시 조기 종료),
데코레이터 2종(`@logged`, `@handle_errors`) 실제 적용, 전 계층 타입 힌트,
다수 클래스 구성, 스택트레이스 없는 예외 처리 + 종료 코드 규칙.

**보너스 4종 모두 구현**:
1. **백업** — `backup` 명령으로 타임스탬프 백업 파일 생성
2. **반복 내역** — `recurring` 명령으로 규칙 등록 후 특정 월에 자동 생성(중복 방지)
3. **출력 테이블 정렬** — 외부 라이브러리 없이 컬럼 폭을 맞춰 출력(금액 우측 정렬)
4. **저장 원자성 강화** — 임시 파일 + `os.replace` 로 update/delete 등을 원자적 교체

---

## 7. 종료 코드

| code | 의미 |
| --- | --- |
| `0` | 정상 종료 |
| `1` | 도메인 오류(검증 실패, 없는 id/카테고리 등) |
| `2` | 예상치 못한 오류 |
| `130` | 사용자 중단(Ctrl+C) |

---

## 8. 시연 스크립트 (`demo.sh`)

모든 기능을 순서대로 보여 주는 시연 스크립트를 함께 넣었습니다.
빈 상태에서 시작해 **24단계**를 거치며 요구사항과 보너스 기능을 전부 실행합니다.

```bash
./demo.sh            # 단계마다 Enter 를 눌러 진행 
./demo.sh --auto     # 멈추지 않고 끝까지 자동 실행
./demo.sh --keep     # 끝난 뒤 시연 데이터를 지우지 않고 남김
./demo.sh --from 17  # 17번 단계부터 보여 주기 (앞 단계는 조용히 수행)
./demo.sh --help     # 사용법
```

- 시연 데이터는 `./demo_data` 에만 쌓이므로 **실제 `./data` 는 건드리지 않습니다.**
- 대화형 명령(`add`, `category add`)은 표준입력으로 답을 흘려 넣어 자동 진행합니다.
- 화면에 찍히는 명령줄에는 `--data-dir ./demo_data` 를 생략해 표시합니다.
- 파이썬 실행기를 바꾸려면 `PYTHON=python3.12 ./demo.sh` 처럼 지정하세요.

### 단계 구성

| 단계 | 보여 주는 것 | 확인 포인트 |
| --- | --- | --- |
| 1 | 초기 실행 | 폴더/파일 자동 생성, 기본 카테고리 5종 |
| 2 | `category add` | 대화형 입력 |
| 3 | `add` × 5 | 거래 추가, `TX-000001` 부터 id 자동 부여 |
| 4 | `add` 검증 실패 | 잘못된 날짜·카테고리·금액 → `[오류]`+`[힌트]` 후 재입력 |
| 5 | `list --limit` | 최신순, 역방향 스트리밍 + 조기 종료 |
| 6 | `list --verbose` | `@logged` 의 START/END + 소요 시간(ms) |
| 7 | `search` | 기간·타입·카테고리 / 메모 키워드·태그 조합 |
| 8 | `budget set/list` | 월 예산 |
| 9 | `summary` | 요약 + 사용률, 데이터 없는 달 처리 |
| 10 | 예산 초과 | `[경고]` 와 초과액 |
| 11 | `update` | 옵션 기반 수정 (원자적 교체) |
| 12 | `delete` | 삭제 |
| 13 | `export` | CSV 내보내기 + 파일 내용 확인 |
| 14 | `import` | 잘못된 행 2개를 건너뛰고 `imported=2, skipped=2` |
| 15 | `category remove` | 사용 중이라 **삭제 거부** (종료 코드 1) |
| 16 | `category remove --replace-with` | 거래 3건 대체 후 삭제 |
| 17 | `recurring add` **[보너스]** | 옵션 방식 + 대화형 방식 |
| 18 | `recurring apply` **[보너스]** | 2월에 "매월 31일" → **2월 29일로 보정**, 재실행 시 0건(중복 방지) |
| 19 | `recurring remove` **[보너스]** | 규칙 삭제 |
| 20 | `backup` **[보너스]** | 타임스탬프 사본 4개 |
| 21 | 예외 처리 | 없는 id / 잘못된 월 / 조건 누락 → 종료 코드 확인 |
| 22 | `--help` | 전체·하위 명령 도움말 |
| 23 | 저장 파일 | JSONL 원본과 `app.log` 직접 확인 |
| 24 | `--data-dir` | 다른 폴더 = 완전히 별개의 가계부 |

---

## 9. 핵심 개념 정리

### 9.1 영속성(Persistence)

프로그램이 끝나면 메모리의 변수는 사라집니다. 다시 켰을 때도 데이터가 남아 있으려면
**파일에 써 두어야** 하고, 이를 영속성이라고 합니다.

이 프로그램은 모든 상태를 `./data` 폴더의 파일에 기록합니다. 메모리에는 어떤 것도
"보관"하지 않고, 필요할 때마다 파일에서 읽습니다. 그래서 종료·재실행·다른 터미널에서의
실행이 모두 같은 데이터를 봅니다. `--data-dir` 로 폴더를 바꾸면 완전히 독립된 가계부가 됩니다.

### 9.2 JSONL — 한 줄에 JSON 하나

`JSON Lines` 는 파일 한 줄이 곧 완결된 JSON 객체 하나인 형식입니다.

```text
{"id": "TX-000001", "type": "income",  "date": "2024-01-05", ...}
{"id": "TX-000002", "type": "expense", "date": "2024-01-12", ...}
```

CSV 대신 JSONL을 고른 이유는 두 가지입니다.

1. **한 줄 = 한 레코드**라서 파일을 처음부터 끝까지 올리지 않고 **한 줄씩 흘려 읽을 수 있다**(→ 9.3).
2. `tags` 처럼 **목록 값**을 따옴표 이스케이프 없이 자연스럽게 담을 수 있다.

CSV는 **외부와 주고받는 교환 포맷**(`import` / `export`)으로 역할을 나눴습니다.
저장 포맷과 교환 포맷이 달라도 되는 이유는, 둘 사이 변환을 서비스 계층이 책임지기 때문입니다.

### 9.3 제너레이터와 스트리밍 — 필요한 만큼만 읽기

일반 함수는 `return` 으로 값을 한 번에 돌려주지만, **제너레이터**는 `yield` 로 값을
**하나씩** 내보내고 그 자리에서 멈춰 기다립니다. 호출한 쪽이 다음 값을 요구할 때 이어서 실행됩니다.

```python
def iter_all(self) -> Iterator[Transaction]:
    for line in _iter_lines(self.path):      # 파일을 한 줄씩
        yield Transaction.from_dict(json.loads(line))   # 한 건씩 내보냄
```

이 방식의 이점은 **메모리 사용량이 데이터 양과 무관**하다는 것입니다. 거래가 10만 건이어도
메모리에는 언제나 한 건만 올라옵니다.

여기서 한 걸음 더 나아간 것이 `list --limit N` 입니다. 최신순 N건만 필요한데 파일 전체를
읽는 것은 낭비이므로, `_iter_lines_reversed()` 가 파일 **끝에서부터** 블록 단위로 거꾸로 읽고,
`list_recent()` 가 N건을 채우는 순간 `break` 로 멈춥니다. 앞쪽 데이터는 **디스크에서 아예
읽지 않습니다**. 이것이 "조기 종료(early exit)"이며, 스트리밍이 주는 진짜 이득입니다.

> 관련 코드: [repository.py](budget_app/repository.py) 의 `_iter_lines`, `_iter_lines_reversed` /
> [services.py](budget_app/services.py) 의 `list_recent`

### 9.4 원자적 쓰기 — 쓰기 도중 실패해도 데이터 일관성을 보장

수정·삭제는 JSONL 파일을 **전체 재작성**해야 합니다. 원본 파일에 직접 덮어쓰다가
중간에 프로그램이 멈추면, 파일은 "절반만 새 내용인" 복구 불가능한 상태가 됩니다.

그래서 쓰기를 두 단계로 나눴습니다.

1. 같은 폴더에 **임시 파일**을 만들고 새 내용을 전부 쓴다.
2. 다 쓰고 나서 `os.replace(임시, 원본)` 으로 **이름을 바꿔치기**한다.

`os.replace` 는 같은 파일시스템 안에서 **원자적(atomic)** 으로 동작합니다. 즉 "옛날 파일"
아니면 "새 파일"이고, 그 중간 상태가 외부에 보이지 않습니다. 1단계에서 실패하면 원본은
손도 대지 않은 상태로 남고, 임시 파일만 지워집니다.

> 관련 코드: [repository.py](budget_app/repository.py) 의 `_atomic_write_lines`

### 9.5 계층 분리

기능을 한 파일에 몰아넣으면, 화면 출력 코드와 파일 저장 코드와 계산 로직이 뒤섞여
한 군데를 고칠 때 다른 곳이 깨집니다. 그래서 **책임별로 계층을 나누고, 의존 방향을
한쪽으로만** 고정했습니다.

```text
cli  ──▶  services  ──▶  repository  ──▶  models
(입출력)   (규칙)         (파일 I/O)       (데이터 구조·검증)
```

| 계층 | 책임지는 것 | 책임지지 않는 것 |
| --- | --- | --- |
| `models` | 데이터의 모양과 "올바른 값"의 정의 | 저장 위치, 화면 출력 |
| `repository` | 파일을 읽고 쓰는 방법(JSONL, 스트리밍, 원자적 교체) | 비즈니스 규칙 |
| `services` | 규칙(카테고리 존재 확인, 중복 방지, 집계, 예산 비교) | 파일 포맷, 입력 방식 |
| `cli` | 인자 파싱, 대화형 질문, 표 정렬 출력 | 규칙, 저장 |

화살표가 한 방향이므로 **아래 계층은 위 계층을 모릅니다**. `BudgetService` 는 자기 결과가
터미널에 표로 출력되는지 CSV로 나가는지 모르고, `TransactionRepository` 는 예산 규칙을
모릅니다. 덕분에 "대화형 대신 옵션으로 받기" 같은 변경이 `cli` 안에서 끝납니다.

### 9.6 데코레이터

로그 남기기, 실행 시간 측정, 예외 처리는 **거의 모든 명령에 필요하지만 그 명령의 본질은
아닌** 일입니다(이런 것을 cross-cutting concern, 횡단 관심사라고 합니다).
이걸 각 함수에 직접 쓰면 12개 명령에 같은 코드가 12번 복사됩니다.

데코레이터는 **함수를 감싸는 함수**입니다. 원래 함수를 받아, 앞뒤에 공통 작업을 덧붙인
새 함수를 돌려줍니다.

```python
@logged                      # ← 이 한 줄이 아래 함수를 감싼다
def cmd_list(service, args):
    _print_tx_table(list(service.list_recent(args.limit)))   # 본래 할 일만 남음
```

이 프로젝트는 두 종류를 씁니다.

- **`@logged`** — 각 명령 함수에 붙어 `START`/`END`와 소요 시간(ms)을 기록합니다.
  출력 위치는 `configure()` 로 주입하므로, 데코레이터가 경로를 직접 알지 않습니다.
- **`@handle_errors`** — 진입점 `run()` 에 한 번 붙어 **예외를 종료 코드로 번역**합니다(→ 9.7).

> 관련 코드: [decorators.py](budget_app/decorators.py)

### 9.7 예외 설계와 종료 코드

이 프로그램은 실패를 두 가지로 나눕니다.

- **예상 가능한 실패** — 날짜 형식 오류, 없는 id, 미등록 카테고리처럼 *사용자가 고칠 수 있는* 것.
  `BudgetError` 를 상속한 `ValidationError` / `NotFoundError` / `CategoryError` 로 표현합니다.
  이 예외들은 **원인(message)과 해결 힌트(hint)를 함께** 담습니다.
- **예상 못 한 실패** — 그 밖의 모든 것. 최종 방어선에서 잡아 요약만 보여줍니다.

```text
[오류] 등록되지 않은 카테고리입니다: '커피'
[힌트] 'category add' 로 등록하거나 기존 카테고리를 사용하세요. 현재: food, transport, ...
```

그리고 실패는 **종료 코드**로도 표현됩니다(7번 표). 사람은 메시지를 읽지만, 이 프로그램을
호출하는 **다른 스크립트는 종료 코드를 읽기** 때문입니다. `budget_app export ... && echo 성공`
같은 조합이 제대로 동작하려면 성공은 `0`, 실패는 `0이 아닌 값`이어야 합니다.

> 관련 코드: [errors.py](budget_app/errors.py), [decorators.py](budget_app/decorators.py) 의 `handle_errors`

### 9.8 타입 힌트

`def validate_amount(value: object) -> int:` 는 "무엇이든 받아서 **정수를 돌려준다**"는
약속입니다. 호출하는 쪽은 반환값이 정수임을 믿고 쓸 수 있고, 함수는 그 약속을 지키기 위해
검증에 실패하면 값을 돌려주는 대신 예외를 던집니다.

타입 힌트는 실행 속도를 바꾸지 않습니다. 대신 (1) 주석 없이도 의도가 드러나고,
(2) 에디터가 자동완성·오류 표시를 해 주며, (3) `mypy` 같은 도구로 실행 전에 불일치를
잡을 수 있습니다. 전 계층에 붙어 있으며, 특히 `-> Iterator[Transaction]` 는
"리스트가 아니라 **제너레이터**를 돌려준다"는 사실을 호출부에 알려 주는 역할을 합니다.

### 9.9 검증(Validation)을 한곳에 모은 이유

날짜가 올바른지 확인해야 하는 곳은 `add`, `update`, `search`, `export`, `import` 등 여럿입니다.
각자 검사하면 규칙이 조금씩 어긋나고, 메시지도 제각각이 됩니다.

그래서 `models.py` 의 `validate_date` / `validate_month` / `validate_type` / `validate_amount` /
`validate_day` 하나씩만 두고 모두가 호출합니다. 이 함수들은 **통과한 값을 정규화해서 반환**하므로
`date = validate_date(raw)` 처럼 검사와 대입을 한 번에 할 수 있습니다.

같은 함수를 대화형 입력에서도 재사용합니다. `_prompt_valid()` 가 검증 함수를 인자로 받아
**통과할 때까지 다시 묻는** 구조라, 옵션 입력과 대화형 입력이 동일한 규칙을 따릅니다.

### 9.10 데이터 정합성 

- **카테고리 삭제** — 그 카테고리를 쓰는 거래가 있으면 그냥 지우지 않습니다. 지우면 거래가
  존재하지 않는 카테고리를 가리키게 되기 때문입니다. `--replace-with` 로 **거래를 먼저 옮긴 뒤**
  삭제합니다.
- **반복 내역 중복 방지** — 규칙마다 `applied` 목록에 이미 생성한 월을 기록합니다. 같은 달에
  `apply` 를 여러 번 실행해도 두 번 생기지 않습니다(멱등, idempotent).
- **없는 날짜 보정** — "매월 31일" 규칙을 2월에 적용하면 2월 31일은 존재하지 않으므로
  `calendar.monthrange()` 로 **그 달의 마지막 날**로 맞춥니다.
- **import 부분 실패 허용** — CSV 한 줄이 잘못됐다고 전체를 취소하면 나머지 정상 데이터도
  버려집니다. 잘못된 행만 건너뛰고 `imported` / `skipped` 건수를 알려 줍니다.

### 9.11 중복 요청과 재시도에도 일관된 결과를 보장

같은 작업을 여러 번 해도 결과가 한 번 한 것과 같은 성질입니다.
`recurring apply --month 2024-03` 이 대표적인 예로, 몇 번을 실행하든 2024-03의 반복 거래는
정확히 한 세트만 존재합니다. 자동화(예: 매달 1일 실행)에서 중복 실행이 사고로 이어지지 않도록
하는 장치입니다.
