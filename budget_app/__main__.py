"""``python -m budget_app`` 로 실행했을 때 가장 먼저 실행되는 파일.
"""

import sys

from .cli import run

if __name__ == "__main__":
    # sys.argv 는 사용자가 터미널에 친 단어들의 목록이다.
    #   python -m budget_app list --limit 5
    #   -> sys.argv = ['.../budget_app/__main__.py', 'list', '--limit', '5']
    # [1:] 로 첫 번째(프로그램 경로)를 빼고 나머지만 넘긴다.
    #
    # sys.exit(숫자) 는 그 숫자를 '종료 코드'로 삼아 프로그램을 끝낸다.
    # run() 이 0(성공) 또는 0이 아닌 값(실패)을 돌려주므로, 그대로 전달한다.
    # 이 값 덕분에 다른 스크립트가 성공/실패를 판단할 수 있다.
    sys.exit(run(sys.argv[1:]))
