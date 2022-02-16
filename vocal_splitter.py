#!/usr/bin/env python3

import os, sys
import argparse, requests
import time

import numpy as np
import soundfile as sf
import torch
from tqdm import tqdm

from lib import dataset
from lib import nets
from lib import spec_utils
import librosa


class Separator(object):

	def __init__(self, model, device, batchsize, cropsize, postprocess = False):
		self.model = model
		self.offset = model.offset
		self.device = device
		self.batchsize = batchsize
		self.cropsize = cropsize
		self.postprocess = postprocess

	def _separate(self, X_mag_pad, roi_size):
		X_dataset = []
		patches = (X_mag_pad.shape[2] - 2 * self.offset) // roi_size
		for i in range(patches):
			start = i * roi_size
			X_mag_crop = X_mag_pad[:, :, start:start + self.cropsize]
			X_dataset.append(X_mag_crop)

		X_dataset = np.asarray(X_dataset)

		self.model.eval()
		with torch.no_grad():
			mask = []
			# To reduce the overhead, dataloader is not used.
			for i in tqdm(range(0, patches, self.batchsize)):
				X_batch = X_dataset[i: i + self.batchsize]
				X_batch = torch.from_numpy(X_batch).to(self.device)

				pred = self.model.predict_mask(X_batch)

				pred = pred.detach().cpu().numpy()
				pred = np.concatenate(pred, axis = 2)
				mask.append(pred)

			mask = np.concatenate(mask, axis = 2)

		return mask

	def _preprocess(self, X_spec):
		X_mag = np.abs(X_spec)
		X_phase = np.angle(X_spec)

		return X_mag, X_phase

	def _postprocess(self, mask, X_mag, X_phase):
		if self.postprocess:
			mask = spec_utils.merge_artifacts(mask)

		y_spec = mask * X_mag * np.exp(1.j * X_phase)
		v_spec = (1 - mask) * X_mag * np.exp(1.j * X_phase)

		return y_spec, v_spec

	def separate(self, X_spec):
		X_mag, X_phase = self._preprocess(X_spec)

		n_frame = X_mag.shape[2]
		pad_l, pad_r, roi_size = dataset.make_padding(n_frame, self.cropsize, self.offset)
		X_mag_pad = np.pad(X_mag, ((0, 0), (0, 0), (pad_l, pad_r)), mode = 'constant')
		X_mag_pad /= X_mag_pad.max()

		mask = self._separate(X_mag_pad, roi_size)
		mask = mask[:, :, :n_frame]

		y_spec, v_spec = self._postprocess(mask, X_mag, X_phase)

		return y_spec, v_spec

	def separate_tta(self, X_spec):
		X_mag, X_phase = self._preprocess(X_spec)

		n_frame = X_mag.shape[2]
		pad_l, pad_r, roi_size = dataset.make_padding(n_frame, self.cropsize, self.offset)
		X_mag_pad = np.pad(X_mag, ((0, 0), (0, 0), (pad_l, pad_r)), mode = 'constant')
		X_mag_pad /= X_mag_pad.max()

		mask = self._separate(X_mag_pad, roi_size)

		pad_l += roi_size // 2
		pad_r += roi_size // 2
		X_mag_pad = np.pad(X_mag, ((0, 0), (0, 0), (pad_l, pad_r)), mode = 'constant')
		X_mag_pad /= X_mag_pad.max()

		mask_tta = self._separate(X_mag_pad, roi_size)
		mask_tta = mask_tta[:, :, roi_size // 2:]
		mask = (mask[:, :, :n_frame] + mask_tta[:, :, :n_frame]) * 0.5

		y_spec, v_spec = self._postprocess(mask, X_mag, X_phase)

		return y_spec, v_spec


def ffm_wav2m4a(input_fn, output_fn, br = '128k'):
	os.system(f"ffmpeg -y -i '{input_fn}' -c:a aac -b:a {br} '{output_fn}'")


def ffm_video2wav(input_fn, output_fn):
	# The built-in DNN model is trained on 44100 sampling rate, it can still run but does not work on other sampling rates
	os.system(f"ffmpeg -y -i '{input_fn}' -f wav -ar 44100 '{output_fn}'")


def split_vocal(in_wav, out_wav_nonvocal, out_wav_vocal, args):
	print('Loading wave source ...', end = ' ', flush = True)
	X, sr = librosa.load(in_wav, args.sr, False, dtype = np.float32, res_type = 'kaiser_fast')
	print('done', flush = True)

	if X.ndim == 1:
		# mono to stereo
		X = np.asarray([X, X])

	print('STFT of wave source ...', end = ' ', flush = True)
	X_spec = spec_utils.wave_to_spectrogram(X, args.hop_length, args.n_fft)
	print('done', flush = True)

	sp = Separator(args.model, args.device, args.batchsize, args.cropsize, args.postprocess)

	if args.tta:
		y_spec, v_spec = sp.separate_tta(X_spec)
	else:
		y_spec, v_spec = sp.separate(X_spec)

	print('Inverse STFT of instruments ...', end = ' ', flush = True)
	wave = spec_utils.spectrogram_to_wave(y_spec, hop_length = args.hop_length)
	print('done', flush = True)
	sf.write(out_wav_nonvocal, wave.T, sr)

	if out_wav_vocal:
		print('Inverse STFT of vocals ...', end = ' ', flush = True)
		wave = spec_utils.spectrogram_to_wave(v_spec, hop_length = args.hop_length)
		print('done', flush = True)
		sf.write(out_wav_vocal, wave.T, sr)


song_path = ''

def get_next_file():
	global song_path
	try:
		obj = requests.get('http://localhost:5000/get_vocal_todo_list').json()
		song_path = obj['download_path'].rstrip('/')
	except:
		if not song_path:
			print('PiKaraoke is not running and --download-path is not specified, exiting ...')
			sys.exit()
		obj = {'queue': []}

	if not os.path.isdir(song_path+'/nonvocal') and not os.path.isdir(song_path+'/vocal'):
		return None
	for fn in obj['queue']:
		if os.path.isdir(song_path+'/nonvocal') and not os.path.isfile(f'{song_path}/nonvocal/{os.path.basename(fn)}.m4a'):
			return os.path.basename(fn)
		if os.path.isdir(song_path+'/vocal') and not os.path.isfile(f'{song_path}/vocal/{os.path.basename(fn)}.m4a'):
			return os.path.basename(fn)

	# get from listing directory
	for bn in [i for i in os.listdir(song_path) if not i.startswith('.') and os.path.isfile(song_path+'/'+i)]:
		if os.path.isdir(song_path+'/nonvocal') and not os.path.isfile(f'{song_path}/nonvocal/{bn}.m4a'):
			return bn
		if os.path.isdir(song_path+'/vocal') and not os.path.isfile(f'{song_path}/vocal/{bn}.m4a'):
			return bn

	return None


def main():
	global song_path

	p = argparse.ArgumentParser()
	p.add_argument('--download-path', '-d', help = "Path for downloaded songs. Will be overridden by the one from HTTP request. "
					"Set this to forcefully run the vocal-splitter even when PiKaraoke is not running.", default = '')
	p.add_argument('--gpu', '-g', type = int, help = 'CUDA device ID for GPU inference, set to -1 to use CPU', default = None)
	p.add_argument('--pretrained_model', '-P', type = str, default = 'models/baseline.pth')
	p.add_argument('--sr', '-r', type = int, default = 44100)
	p.add_argument('--n_fft', '-f', type = int, default = 2048)
	p.add_argument('--hop_length', '-H', type = int, default = 1024)
	p.add_argument('--batchsize', '-B', type = int, default = 4)
	p.add_argument('--cropsize', '-c', type = int, default = 256)
	p.add_argument('--postprocess', '-p', action = 'store_true')
	p.add_argument('--tta', '-t', action = 'store_true')
	args = p.parse_args()

	song_path = os.path.expanduser(args.download_path).rstrip('/')

	# Load and initialize DNN model
	print('Loading vocal-splitter model ...', end = ' ', flush = True)
	device = torch.device('cpu')
	model = nets.CascadedNet(args.n_fft)
	model.load_state_dict(torch.load(args.pretrained_model, map_location = device))
	if (args.gpu is None or args.gpu >= 0) and torch.cuda.is_available():
		device = torch.device(f'cuda:{0 if args.gpu is None else args.gpu}')
		model.to(device)
	args.model = model
	args.device = device
	print('done')

	# set song_path global variable from local server
	get_next_file()

	# Create temporary filenames if not done yet
	in_wav, out_wav_vocal, out_wav_nonvocal, out_m4a_vocal, out_m4a_nonvocal = \
		[song_path+'/.'+bn for bn in ['input.wav', 'vocal.wav', 'nonvocal.wav', 'vocal.m4a', 'nonvocal.m4a']]

	# Main loop
	while True:
		next_file = get_next_file()
		if not next_file:
			time.sleep(2)
			continue

		# run vocal splitter on next_file
		ffm_video2wav(song_path+'/'+next_file, in_wav)
		split_vocal(in_wav, out_wav_nonvocal, out_wav_vocal, args)
		if os.path.isdir(song_path+'/nonvocal'):
			ffm_wav2m4a(out_wav_nonvocal, out_m4a_nonvocal)
			os.rename(out_m4a_nonvocal, f'{song_path}/nonvocal/{next_file}.m4a')
		if os.path.isdir(song_path+'/vocal'):
			ffm_wav2m4a(out_wav_vocal, out_m4a_vocal)
			os.rename(out_m4a_vocal, f'{song_path}/vocal/{next_file}.m4a')


if __name__ == '__main__':
	main()
