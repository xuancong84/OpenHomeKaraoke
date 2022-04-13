#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import sys
from googletrans import Translator


def find_lt(arr, n_limit):
	n = len(arr)
	while sum(arr[:n])>n_limit:
		new_n = int(n*n_limit/sum(arr[:n]))
		n = min(n-1, new_n)
	return n


def split_by_char(arr, n_limit):
	ret = []
	cur_start = 0
	while not ret or ret[-1][1]<len(arr):
		n = cur_start + find_lt(arr[cur_start:], n_limit)
		ret += [(cur_start, n)]
		cur_start = n
	return ret


def main():
	parser = argparse.ArgumentParser(
		description = 'Python Google Translator as a command-line tool')
	parser.add_argument('text', help = 'The text you want to translate.', nargs = '?')
	parser.add_argument('-d', '--dest', default = 'en',
	                    help = 'The destination language you want to translate. (Default: en)')
	parser.add_argument('-s', '--src', default = 'auto',
	                    help = 'The source language you want to translate. (Default: auto)')
	parser.add_argument('-c', '--detect', action = 'store_true', default = False,
	                    help = 'Detect source language, print language type and confidence score')
	parser.add_argument('-f', '--file', default = '',
	                    help = 'Input file, this has the highest priority')
	parser.add_argument('-n', '--split-threshold', type = int, default = 5000,
	                    help = 'Character limit for splitting into multiple batches')
	args = parser.parse_args()
	translator = Translator()

	if args.detect:
		result = translator.detect(args.text)
		print(result.lang, result.confidence)
		return

	if args.file:
		text = open(args.file, 'rt').read()
	elif args.text is None:
		text = sys.stdin.read()
	else:
		text = args.text

	arr = text.splitlines()
	if len(arr)>1:
		bnds = split_by_char([len(L.encode('utf-8', 'ignore'))+1 for L in arr], args.split_threshold)
		chunks = ['\n'.join(arr[p1:p2]) for p1, p2 in bnds]
		for chunk in chunks:
			result = translator.translate(chunk, dest = args.dest, src = args.src)
			print(result.text)
	else:
		result = translator.translate(text, dest = args.dest, src = args.src)
		print(result.text)


if __name__ == '__main__':
	main()
