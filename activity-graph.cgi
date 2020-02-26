#!/bin/bash

# timecolumn(N, "timefmt")

# Sample time 2018-06-20 06:27:02.446

function countlogs() {
    grep -a "W1XM      $1" /var/log/aprx/aprx-rf.log | cut -f 1 -d ':' | uniq -c
}

days=${QUERY_STRING:-30}

echo "Content-type: image/svg+xml"
echo

gnuplot <(cat <<EOF
#set terminal dumb
set terminal svg size 1920,1080 dynamic mouse jsdir "js"
set xdata time
set timefmt "%Y/%m/%d"
set xrange ["$(date +%Y/%m/%d --date="$days days ago")":]
#set xrange ["03/21/95":"03/22/95"]
set format x "%Y/%m/%d"
set timefmt "%Y-%m-%d %H:%M"
set ylabel "packets/hour"
set grid xtics ytics
set boxwidth 3600
plot "<&3" using 2:1 title "RX" with steps, "<&4" using 2:1 title "TX" with steps
EOF
) 3< <(countlogs R) 4< <(countlogs T)
