#!/bin/zsh
# mark.sh TASK start|end [note]  -> appends epoch + iso to markers.tsv
D=${0:A:h}
[ -f $D/markers.tsv ] || printf "epoch\tiso\ttask\tevent\tnote\n" > $D/markers.tsv
printf "%s\t%s\t%s\t%s\t%s\n" $(date +%s) $(date -u +%Y-%m-%dT%H:%M:%SZ) $1 $2 "$3" >> $D/markers.tsv
