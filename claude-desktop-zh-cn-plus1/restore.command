#!/bin/zsh
cd -- "${0:A:h}"
print '请先保存工作并按 ⌘Q 退出 Claude。'
/usr/bin/python3 patcher.py --restore --launch "$@"
result=$?
if (( result != 0 )); then
  read '?未完成恢复，请查看上方提示。按回车退出。'
fi
exit $result
