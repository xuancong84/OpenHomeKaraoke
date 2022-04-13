#!/bin/bash

if [ "$1" == "-c" ]; then
	mv lang/en_US lang/zh_CN .
	rm lang/*
	mv en_US zh_CN lang/
fi


N=`cat lang/en_US 2>/dev/null | wc -l`
cat langs.list | sed "/en$/d; /zh-/d" \
| while read line; do
	lang_full="`echo $line | awk 'BEGIN{FS=\",\"}{print $1}'`"
	lang_short="`echo $line | awk 'BEGIN{FS=\",\"}{print $2}'`"
	
	M=`cat lang/$lang_short 2>/dev/null | wc -l`
	if [ "$N" == "$M" ]; then
		continue
	fi
	
	echo $lang_full "==>" lang/$lang_short
	(echo $lang_full; sed -n '2,$p' lang/en_US) | ./translate.py -s en -d $lang_short >lang/$lang_short
	
	if [ ! -s lang/$lang_short ]; then
		rm -f lang/$lang_short
	fi
	
	sleep 1
	done


if [ `cat lang/zh_CN 2>/dev/null | wc -l` != `cat lang/zh_TW 2>/dev/null | wc -l` ]; then
  (echo 汉语; sed -n '2,$p' lang/zh_CN) | ./translate.py -s zh-CN -d zh-TW >lang/zh_TW
  echo zh_TW "==>" lang/zh_TW
fi

if [ ! -s lang/zh_TW ]; then
	rm -f lang/zh_TW
fi
