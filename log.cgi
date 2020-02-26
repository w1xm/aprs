#!/bin/bash
echo 'Content-type: text/html'
echo
echo '<PRE>'
case "$QUERY_STRING" in 
    all)
	tail -1000 /var/log/aprx/aprx-rf.log | sort -r;;
    *)
	grep -a 'W1XM      [RT]' /var/log/aprx/aprx-rf.log | tail -1000 | sort -r;;
esac
echo '</PRE>'
