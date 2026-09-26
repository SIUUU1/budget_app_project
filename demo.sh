#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# budget_app 시연 스크립트
#
#   사용법:
#     ./demo.sh            # 단계마다 Enter 를 눌러 진행 (발표용)
#     ./demo.sh --auto     # 멈추지 않고 끝까지 자동 실행
#     ./demo.sh --keep     # 끝난 뒤 demo_data 폴더를 지우지 않고 남김
#     ./demo.sh --from 7   # 7번 단계부터 실행 (앞 단계는 조용히 수행)
#
#   시연용 데이터는 ./demo_data 에만 쌓이므로 실제 ./data 는 건드리지 않습니다.
# ---------------------------------------------------------------------------
set -uo pipefail

cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
DATA_DIR="./demo_data"
AUTO=0
KEEP=0
FROM=1
STEP=0

while [ $# -gt 0 ]; do
    case "$1" in
        --auto) AUTO=1 ;;
        --keep) KEEP=1 ;;
        --from) FROM="$2"; shift ;;
        -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
        *) echo "알 수 없는 옵션: $1"; exit 2 ;;
    esac
    shift
done

# --------------------------- 출력 헬퍼 ------------------------------------- #
BOLD=$'\033[1m'; DIM=$'\033[2m'; CYAN=$'\033[36m'; YELLOW=$'\033[33m'; OFF=$'\033[0m'
[ -t 1 ] || { BOLD=""; DIM=""; CYAN=""; YELLOW=""; OFF=""; }

SHOW=1   # 현재 단계를 화면에 보여줄지 (--from 이전 단계는 0)

step() {   # step "제목" "설명"
    STEP=$((STEP + 1))
    if [ "$STEP" -lt "$FROM" ]; then SHOW=0; return; fi
    SHOW=1
    printf '\n%s\n' "${CYAN}────────────────────────────────────────────────────────────${OFF}"
    printf '%s\n' "${BOLD}[${STEP}] $1${OFF}"
    [ -n "${2:-}" ] && printf '%s\n' "${DIM}    $2${OFF}"
    printf '%s\n' "${CYAN}────────────────────────────────────────────────────────────${OFF}"
    if [ "$AUTO" -eq 0 ]; then
        printf '%s' "${DIM}    (Enter 로 실행)${OFF}"
        read -r _ </dev/tty || true
    fi
}

note() { [ "$SHOW" -eq 1 ] && printf '%s\n' "${YELLOW}>> $1${OFF}"; return 0; }

# 현재 단계를 보여주는 중일 때만 실행하는 보조 명령(cat/ls/head/tail 등).
show() { [ "$SHOW" -eq 1 ] && "$@"; return 0; }

# 명령 한 줄을 화면에 보여준 뒤 실행한다.
run() {
    if [ "$SHOW" -eq 1 ]; then
        printf '%s\n' "${DIM}\$ python -m budget_app $*${OFF}"
        "$PY" -m budget_app "$@" --data-dir "$DATA_DIR"
    else
        "$PY" -m budget_app "$@" --data-dir "$DATA_DIR" >/dev/null 2>&1
    fi
}

# 대화형 명령: 표준입력으로 답을 흘려 넣는다.
run_stdin() {
    local input="$1"; shift
    if [ "$SHOW" -eq 1 ]; then
        printf '%s\n' "${DIM}\$ python -m budget_app $*   ${OFF}${DIM}(대화형 입력: $(echo "$input" | tr '\n' '/'))${OFF}"
        printf '%s' "$input" | "$PY" -m budget_app "$@" --data-dir "$DATA_DIR"
    else
        printf '%s' "$input" | "$PY" -m budget_app "$@" --data-dir "$DATA_DIR" >/dev/null 2>&1
    fi
}

# 실패가 정상인 명령: 종료 코드를 확인해서 보여준다.
run_expect_fail() {
    if [ "$SHOW" -eq 1 ]; then
        printf '%s\n' "${DIM}\$ python -m budget_app $*${OFF}"
        "$PY" -m budget_app "$@" --data-dir "$DATA_DIR"
        local code=$?
        printf '%s\n' "${YELLOW}>> 종료 코드: ${code}  (0이 아니므로 자동화 스크립트가 실패를 감지할 수 있다)${OFF}"
    else
        "$PY" -m budget_app "$@" --data-dir "$DATA_DIR" >/dev/null 2>&1
    fi
    return 0
}

# --------------------------- 준비 ------------------------------------------ #
command -v "$PY" >/dev/null 2>&1 || { echo "python3 를 찾을 수 없습니다. PYTHON=... 로 지정하세요."; exit 2; }

printf '%s\n' "${BOLD}budget_app 시연 — 데이터 폴더: ${DATA_DIR}${OFF}"
printf '%s\n' "${DIM}아래 모든 명령에는 --data-dir ${DATA_DIR} 가 자동으로 붙습니다(화면에서는 생략).${OFF}"
"$PY" --version
rm -rf "$DATA_DIR" demo_export.csv demo_import.csv

# --------------------------------------------------------------------------- #
step "초기 실행 — 저장 폴더/기본 카테고리 자동 생성" \
     "저장 파일이 없으면 폴더를 만들고 기본 카테고리(food, transport, rent, salary, etc)를 넣는다."
run category list
note "생성된 파일: $(ls "$DATA_DIR" 2>/dev/null | tr '\n' ' ')"

step "category add — 대화형 입력" \
     "옵션 없이 실행하면 카테고리명을 물어본다."
run_stdin 'cafe
' category add
run category list

step "add — 거래 추가(대화형)" \
     "날짜/타입/카테고리/금액/메모/태그를 차례로 묻고 TX-000001 부터 id 를 자동 부여한다."
run_stdin '2024-01-05
income
salary
3000000
1월 급여
fixed
' add
run_stdin '2024-01-12
expense
transport
20000
지하철 정기권

' add
run_stdin '2024-01-15
expense
food
15000
점심
meal
' add
run_stdin '2024-01-20
expense
rent
150000
월세
fixed
' add
run_stdin '2024-01-22
expense
food
30000
저녁 회식
meal
' add

step "add 검증 실패 — 재입력 요구" \
     "잘못된 날짜/금액/카테고리를 넣으면 [오류]+[힌트] 를 보여주고 다시 물어본다."
run_stdin '2024-13-99
2024-01-25
expense
없는카테고리
cafe
-500
4500
아메리카노
meal
' add

step "list — 최신순 목록 (제너레이터 스트리밍)" \
     "파일을 끝에서부터 한 줄씩 읽고 --limit 에 도달하면 즉시 멈춘다. 파일 전체를 메모리에 올리지 않는다."
run list --limit 3
note "--limit 없이 전체 보기:"
run list

step "list --verbose — 실행 로그/시간 측정 (@logged 데코레이터)" \
     "각 명령 함수를 감싸 START/END 와 소요 시간(ms)을 남긴다. 기능 코드에는 로깅 코드가 없다."
run list --limit 2 --verbose

step "search — 조건 검색" \
     "기간 / 카테고리 / 타입 / 메모 키워드 / 태그를 조합해 검색한다."
run search --from 2024-01-01 --to 2024-01-31 --type expense --category food
note "메모 키워드 + 태그 검색:"
run search --q 점심 --tag meal

step "budget — 월 예산 설정/조회"
run budget set --month 2024-01 --amount 500000
run budget list

step "summary — 월별 요약 + 예산 사용률"
run summary --month 2024-01 --top 3
note "데이터가 없는 달:"
run summary --month 2023-12

step "예산 초과 경고" \
     "큰 지출을 추가하면 summary 에 [경고] 와 초과액이 함께 표시된다."
run_stdin '2024-01-28
expense
etc
400000
노트북 수리

' add
run summary --month 2024-01 --top 3

step "update — 거래 수정 (옵션 기반)" \
     "수정은 임시 파일에 전부 쓴 뒤 os.replace 로 한 번에 교체하므로 중간에 죽어도 원본이 깨지지 않는다."
run update --id TX-000003 --amount 18000 --memo "점심(금액 정정)"
run search --q 정정

step "delete — 거래 삭제" \
     "삭제도 전체 재작성 + 원자적 교체로 처리한다."
note "삭제 전:"
run list --limit 2
run delete --id TX-000006
note "삭제 후 (TX-000006 아메리카노가 사라짐):"
run list --limit 2

step "export — CSV 내보내기" \
     "--month 또는 --from/--to 중 하나 이상이 필수다."
run export --out demo_export.csv --month 2024-01
note "내보낸 파일 내용:"
show cat demo_export.csv

step "import — CSV 가져오기" \
     "형식이 틀리거나 없는 카테고리인 행은 건너뛰고(skipped) 건수를 알려준다."
cat > demo_import.csv <<'CSV'
date,type,category,amount,memo,tags
2024-02-01,expense,food,12000,김밥,meal
2024-02-03,income,salary,3000000,2월 급여,fixed
2024-02-05,expense,없는카테고리,9000,건너뛰어야 함,
2024-02-07,expense,food,notanumber,금액이 숫자가 아님,
CSV
note "입력 CSV (마지막 2줄은 일부러 잘못된 행):"
show cat demo_import.csv
run import --from demo_import.csv
run summary --month 2024-02

step "category remove — 사용 중이면 삭제 거부" \
     "그 카테고리를 쓰는 거래가 있으면 삭제를 막는다."
run_expect_fail category remove --name food

step "category remove --replace-with — 대체 후 삭제" \
     "거래를 다른 카테고리로 옮긴 뒤 삭제한다."
run category remove --name food --replace-with etc
run category list
run search --category etc

step "recurring add — 반복 내역 등록 [보너스]" \
     "월급/월세처럼 매달 반복되는 항목을 규칙으로 등록한다. 옵션 방식과 대화형 둘 다 된다."
run recurring add --type income --day 25 --category salary --amount 3000000 --memo 월급
note "대화형 방식 (매월 31일 월세 — 2월에는 말일로 보정됨):"
run_stdin 'expense
31
rent
150000
월세
fixed
' recurring add
run recurring list

step "recurring apply — 해당 월 거래 자동 생성 [보너스]" \
     "2월 31일은 존재하지 않으므로 그 달의 마지막 날(2월 29일)로 보정된다."
run recurring apply --month 2024-02
note "같은 달에 다시 실행 — 중복 생성되지 않는다:"
run recurring apply --month 2024-02
run recurring list

step "recurring remove — 규칙 삭제 [보너스]"
run recurring remove --id R-000002
run recurring list

step "backup — 타임스탬프 백업 [보너스]" \
     "모든 저장 파일을 data/backups/ 아래 사본으로 복사한다."
run backup
note "백업 폴더:"
show ls -1 "$DATA_DIR/backups"

step "예외 처리 + 종료 코드" \
     "스택트레이스 대신 [오류] 원인 + [힌트] 해결 방법을 보여주고 0이 아닌 코드로 끝난다."
note "없는 id 수정 (도메인 오류 → 1):"
run_expect_fail update --id TX-999999 --amount 1000
note "잘못된 월 형식 (검증 실패 → 1):"
run_expect_fail summary --month 2024-13
note "export 조건 누락 (검증 실패 → 1):"
run_expect_fail export --out demo_export.csv
note "정상 명령의 종료 코드 확인:"
run category list >/dev/null && show printf '%s\n' "${YELLOW}>> 종료 코드: 0${OFF}"

step "--help — 모든 명령의 사용법"
show printf '%s\n' "${DIM}\$ python -m budget_app --help${OFF}"
show "$PY" -m budget_app --help
note "하위 명령 도움말:"
show printf '%s\n' "${DIM}\$ python -m budget_app recurring --help${OFF}"
show "$PY" -m budget_app recurring --help

step "저장 파일 확인 — 프로그램을 껐다 켜도 남는 데이터" \
     "JSONL(한 줄에 JSON 하나)로 저장한다."
if [ "$SHOW" -eq 1 ]; then
    for f in transactions categories budgets recurring; do
        printf '%s\n' "${BOLD}--- $DATA_DIR/$f.jsonl ---${OFF}"
        head -3 "$DATA_DIR/$f.jsonl"
    done
    printf '%s\n' "${BOLD}--- $DATA_DIR/app.log (마지막 5줄) ---${OFF}"
    tail -5 "$DATA_DIR/app.log"
fi

step "--data-dir — 저장 폴더 분리" \
     "다른 폴더를 지정하면 완전히 별개의 가계부가 된다."
if [ "$SHOW" -eq 1 ]; then
    printf '%s\n' "${DIM}\$ python -m budget_app category list --data-dir ./demo_data_other${OFF}"
    "$PY" -m budget_app category list --data-dir ./demo_data_other
    printf '%s\n' "${DIM}\$ python -m budget_app list --data-dir ./demo_data_other${OFF}"
    "$PY" -m budget_app list --data-dir ./demo_data_other
fi
rm -rf ./demo_data_other

# --------------------------- 마무리 ---------------------------------------- #
printf '\n%s\n' "${BOLD}시연 종료.${OFF}"
if [ "$KEEP" -eq 1 ]; then
    printf '%s\n' "데이터는 ${DATA_DIR} 에 남겨 두었습니다."
else
    rm -rf "$DATA_DIR" demo_export.csv demo_import.csv
    printf '%s\n' "시연용 파일(${DATA_DIR}, demo_export.csv, demo_import.csv)을 정리했습니다. (--keep 으로 보존 가능)"
fi
