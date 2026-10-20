#!/bin/zsh
# Logging wrapper: npcl.sh TASK npc-subcommand args...
# Saves full output to raw/NNN_TASK_SUB.txt and appends a row to calls.tsv
# (seq, task, subcommand, start_iso, start_epoch, seconds, exit_code, status_lines, raw_file).
D=${0:A:h}
TASK=$1; shift
SUB=$1
mkdir -p $D/raw
N=$(( $(ls $D/raw | wc -l) + 1 ))
F=$(printf "%s/raw/%03d_%s_%s.txt" $D $N $TASK $SUB)
START_ISO=$(date -u +%Y-%m-%dT%H:%M:%SZ)
T0=$(.venv/bin/python -c 'import time;print(time.time())')
{ echo "\$ npc $*"; echo "# task=$TASK start=$START_ISO"; } > $F
.venv/bin/npc "$@" >> $F 2>&1
RC=$?
T1=$(.venv/bin/python -c 'import time;print(time.time())')
SECS=$(.venv/bin/python -c "print(round($T1-$T0,2))")
echo "# exit=$RC seconds=$SECS" >> $F
STAT=$(grep -E 'VERIFIED|UNREALIZABLE|COMPILED|COUNTEREXAMPLE|TIMEOUT|UNKNOWN|RESOURCE_LIMIT|SOLVED|EXHAUSTED|NotCausal|FAIL|Error|error' $F | head -5 | tr '\t\n' '  ')
[ -f $D/calls.tsv ] || printf "seq\ttask\tsub\tstart_iso\tstart_epoch\tseconds\texit\tstatus\traw\n" > $D/calls.tsv
printf "%d\t%s\t%s\t%s\t%s\t%s\t%d\t%s\t%s\n" $N $TASK $SUB $START_ISO $T0 $SECS $RC "$STAT" ${F:t} >> $D/calls.tsv
cat $F
