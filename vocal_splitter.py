#!/usr/bin/env python3

import os, sys, time, shutil
import argparse, requests, subprocess

import numpy as np
import soundfile as sf
import torch
torch.backends.quantized.engine = 'qnnpack'
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
	input_fn, output_fn = [fn.replace('"', '\\"') for fn in [input_fn, output_fn]]
	subprocess.run(['ffmpeg', '-y', '-i', input_fn, '-c:a', 'aac', '-b:a', br, output_fn])


def ffm_video2wav(input_fn, output_fn):
	# The built-in DNN model is trained on 44100 sampling rate, it can still run but does not work on other sampling rates
	input_fn, output_fn = [fn.replace('"', '\\"') for fn in [input_fn, output_fn]]
	subprocess.run(['ffmpeg', '-y', '-i', input_fn, '-f', 'wav', '-ar', '44100', output_fn])


def split_vocal_by_stereo(in_wav, out_wav_nonvocal, out_wav_vocal):
	try:
		# Create temporary filenames if not done yet
		X, sr = librosa.load(in_wav, sr=44100, mono=False, dtype = np.float32, res_type = 'kaiser_fast')
		if X.shape[0] < 2:
			return False
		if out_wav_nonvocal:
			sf.write(out_wav_nonvocal, X[0, :] - X[1, :], sr)
		if out_wav_vocal:
			sf.write(out_wav_vocal, X[0, :] + X[1, :], sr)
		return True
	except:
		return False


def split_vocal_by_dnn(in_wav, out_wav_nonvocal, out_wav_vocal, args):
	print('Loading wave source ...', end = ' ', flush = True)
	X, sr = librosa.load(in_wav, sr=args.sr, mono=False, dtype = np.float32, res_type = 'kaiser_fast')
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
last_completed = ''
use_DNN = True

def get_next_file(cuda_device):
	global song_path, use_DNN, last_completed
	try:
		obj = requests.get(f'http://localhost:5000/get_vocal_todo_list/{cuda_device.type}',
		                   headers = {'last_completed': last_completed.encode('utf-8', 'ignore')}).json()
		song_path = obj['download_path'].rstrip('/')
		use_DNN = obj['use_DNN']
	except:
		if not song_path:
			print('PiKaraoke is not running and --download-path is not specified, exiting ...')
			sys.exit()
		obj = {'queue': []}

	if not os.path.isdir(song_path+'/nonvocal') and not os.path.isdir(song_path+'/vocal'):
		return None
	for fn in obj['queue']:
		bn = ('' if use_DNN else '.')+os.path.basename(fn)
		if os.path.isdir(song_path+'/nonvocal') and not os.path.isfile(f'{song_path}/nonvocal/{bn}.m4a'):
			return os.path.basename(fn)
		if os.path.isdir(song_path+'/vocal') and not os.path.isfile(f'{song_path}/vocal/{bn}.m4a'):
			return os.path.basename(fn)

	# get from listing directory
	for bn in [i for i in os.listdir(song_path) if not i.startswith('.') and os.path.isfile(song_path+'/'+i)]:
		bn1 = ('' if use_DNN else '.')+bn
		if os.path.isdir(song_path+'/nonvocal') and not os.path.isfile(f'{song_path}/nonvocal/{bn1}.m4a'):
			return bn
		if os.path.isdir(song_path+'/vocal') and not os.path.isfile(f'{song_path}/vocal/{bn1}.m4a'):
			return bn

	return None


def main(argv):
	global song_path, last_completed

	p = argparse.ArgumentParser()
	p.add_argument('--download-path', '-d', help = "Path for downloaded songs. Will be overridden by the one from HTTP request. "
					"Set this to forcefully run the vocal-splitter even when PiKaraoke is not running.", default = '')
	p.add_argument('--gpu', '-g', type = int, help = 'CUDA device ID for GPU inference, set to -1 to force to use CPU (default will try to use GPU if available)', default = None)
	p.add_argument('--pretrained_model', '-P', type = str, default = 'models/baseline.pth')
	p.add_argument('--sr', '-r', type = int, default = 44100)
	p.add_argument('--n_fft', '-f', type = int, default = 2048)
	p.add_argument('--hop_length', '-H', type = int, default = 1024)
	p.add_argument('--batchsize', '-B', type = int, default = 4)
	p.add_argument('--cropsize', '-c', type = int, default = 256)
	p.add_argument('--postprocess', '-p', action = 'store_true')
	p.add_argument('--tta', '-t', action = 'store_true')
	p.add_argument('--ramdir', '-rd', help = 'Temporary directory on RAMDISK to reduce I/O load',
	               default = 'z:/' if sys.platform.startswith('win') else '/dev/shm')
	args = p.parse_args(argv)

	song_path = os.path.expanduser(args.download_path).rstrip('/')

	# Determine the GPU device and load the DNN model
	print('Loading vocal-splitter model ...', end = ' ', flush = True)
	device = torch.device('cpu')
	model = nets.CascadedNet(args.n_fft)
	model.load_state_dict(torch.load(args.pretrained_model, map_location = device))
	if (args.gpu is None or args.gpu >= 0) and torch.cuda.is_available():
		device = torch.device(f'cuda:{0 if args.gpu is None else args.gpu}')
		model.to(device)
	args.model = model
	args.device = device
	print('done', flush = True)

	# set song_path global variable from local server
	get_next_file(device)

	# Use RAMDISK for large temporary .wav files for speed up if available
	RAMDIR = args.ramdir if os.path.isdir(args.ramdir) else song_path

	# Create temporary filenames if not done yet
	in_wav, out_wav_vocal, out_wav_nonvocal, out_m4a_vocal, out_m4a_nonvocal = \
		[f'{RAMDIR}/.input.wav', f'{RAMDIR}/.vocal.wav', f'{RAMDIR}/.nonvocal.wav', f'{song_path}/.vocal.m4a', f'{song_path}/.nonvocal.m4a']

	# Main loop
	while True:
		next_file = get_next_file(device)
		if not next_file:
			time.sleep(2)
			continue

		# run vocal splitter on next_file
		print(f'Start processing {next_file} :')
		ffm_video2wav(song_path+'/'+next_file, in_wav)

		if use_DNN:
			split_vocal_by_dnn(in_wav, out_wav_nonvocal, out_wav_vocal, args)
			if os.path.isdir(song_path+'/nonvocal'):
				ffm_wav2m4a(out_wav_nonvocal, out_m4a_nonvocal)
				shutil.move(out_m4a_nonvocal, f'{song_path}/nonvocal/{next_file}.m4a')
			if os.path.isdir(song_path+'/vocal'):
				ffm_wav2m4a(out_wav_vocal, out_m4a_vocal)
				shutil.move(out_m4a_vocal, f'{song_path}/vocal/{next_file}.m4a')
		else:
			split_vocal_by_stereo(in_wav, out_wav_nonvocal, out_wav_vocal)
			if os.path.isdir(song_path+'/nonvocal'):
				ffm_wav2m4a(out_wav_nonvocal, out_m4a_nonvocal)
				shutil.move(out_m4a_nonvocal, f'{song_path}/nonvocal/.{next_file}.m4a')
			if os.path.isdir(song_path+'/vocal'):
				ffm_wav2m4a(out_wav_vocal, out_m4a_vocal)
				shutil.move(out_m4a_vocal, f'{song_path}/vocal/.{next_file}.m4a')
		last_completed = next_file


if __name__ == '__main__':
	main(sys.argv[1:])
