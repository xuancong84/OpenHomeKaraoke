#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse, time, random
import os, sys, gzip
from tqdm import tqdm
from googletrans import Translator


def Open(fn, mode='r', **kwargs):
	if fn == '-':
		return open(sys.stdin.fileno(), mode) if mode.startswith('r') else sys.stdout
	fn = os.path.expanduser(fn)
	return gzip.open(fn, mode, **kwargs) if fn.lower().endswith('.gz') else open(fn, mode, **kwargs)


def translate(txt, src, dst):
	while True:
		try:
			return os.translator.translate(txt, dest = dst, src = src).text
		except:
			os.translator = Translator()
			time.sleep(random.randint(1,5))

def main():
	parser = argparse.ArgumentParser(
		description = 'Python Google Translator as a command-line tool')
	parser.add_argument('text', help = 'The text you want to translate.', nargs = '?')
	parser.add_argument('-d', '--dest', default = 'en', help = 'The destination language you want to translate. (Default: en)')
	parser.add_argument('-s', '--src', default = 'auto', help = 'The source language you want to translate. (Default: auto)')
	parser.add_argument('-c', '--detect', action = 'store_true', default = False, help = 'Detect source language, print language type and confidence score')
	parser.add_argument('-i', '--file', default = '', help = 'Input file, this has the highest priority')
	parser.add_argument('-o', '--output', default = '-', help = 'Output file, Default: - for STDOUT')
	parser.add_argument('-n', '--split-threshold', type = int, default = 5000, help = 'Character limit for splitting into multiple batches')
	args = parser.parse_args()
	os.translator = Translator()

	fp_out = Open(args.output, 'w')

	if args.detect:
		result = os.translator.detect(args.text)
		print(result.lang, result.confidence, file=fp_out)
		return

	if args.file:
		text = open(args.file, 'rt').read()
	elif args.text is None:
		text = open(sys.stdin.fileno()).read()
	else:
		text = args.text

	cur_chunk = ''
	for L in tqdm(text.splitlines()):
		L = L.strip()
		if not L:
			if cur_chunk:
				text = translate(cur_chunk, args.src, args.dest)
				print(text, flush=True, file=fp_out)
				cur_chunk = ''
			print(flush=True, file=fp_out)
		elif len(cur_chunk)+1+len(L) > args.split_threshold:
			if cur_chunk:
				result = translate(cur_chunk, args.src, args.dest)
				print(text, flush=True, file=fp_out)
			cur_chunk = L
		else:
			cur_chunk += ('\n' if cur_chunk else '')+L
	
	if cur_chunk:
		result = translate(cur_chunk, args.src, args.dest)
		print(text, flush=True, file=fp_out)


if __name__ == '__main__':
	main()
