import argparse
import os, sys, tempfile

import numpy as np
import soundfile as sf
import torch
from tqdm import tqdm
from scipy.io import wavfile

from lib import dataset
from lib import nets
from lib import spec_utils
from lib import utils


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


class FFMPEG(object):
	def wav2m4a(self, input_fn, output_fn, br = '128k'):
		os.system(f"ffmpeg -i {input_fn} -c:a aac -b:a {br} {output_fn}")

	def video2wav(self, input_fn, output_fn):
		# The built-in DNN model is trained with 44100 sampling rate, it does not work on other sampling rates
		os.system(f"ffmpeg -i {input_fn} -f wav -ar 44100 {output_fn}")


def loadWav(self, wav_fn):
	sr, data = wavfile.read(wav_fn)
	data = data.transpose().astype(np.float32)/32768
	return data, sr

def saveWav(self, wav_data):
	pass


def process_file(in_mp4_fn, out_m4a_nonvocal, out_m4a_vocal):
	pass

def split_vocal(in_wav, out_wav_nonvocal, out_wav_vocal, args):
	print('Loading wave source ...', end = ' ')
	X, sr = loadWav(in_wav)
	print('done')

	if X.ndim == 1:
		# mono to stereo
		X = np.asarray([X, X])

	print('STFT of wave source ...', end = ' ')
	X_spec = spec_utils.wave_to_spectrogram(X, args.hop_length, args.n_fft)
	print('done')

	sp = Separator(args.model, args.device, args.batchsize, args.cropsize, args.postprocess)

	if args.tta:
		y_spec, v_spec = sp.separate_tta(X_spec)
	else:
		y_spec, v_spec = sp.separate(X_spec)

	print('Inverse STFT of instruments ...', end = ' ')
	wave = spec_utils.spectrogram_to_wave(y_spec, hop_length = args.hop_length)
	print('done')
	sf.write('{}_Instruments.wav'.format(out_wav_nonvocal), wave.T, sr)

	if out_wav_vocal:
		print('Inverse STFT of vocals ...', end = ' ')
		wave = spec_utils.spectrogram_to_wave(v_spec, hop_length = args.hop_length)
		print('done')
		sf.write('{}_Vocals.wav'.format(out_wav_vocal), wave.T, sr)


def main():
	p = argparse.ArgumentParser()
	p.add_argument('--gpu', '-g', type = int, default = -1)
	p.add_argument('--pretrained_model', '-P', type = str, default = 'models/baseline.pth')
	p.add_argument('--input', '-i', required = True)
	p.add_argument('--sr', '-r', type = int, default = 44100)
	p.add_argument('--n_fft', '-f', type = int, default = 2048)
	p.add_argument('--hop_length', '-H', type = int, default = 1024)
	p.add_argument('--batchsize', '-B', type = int, default = 4)
	p.add_argument('--cropsize', '-c', type = int, default = 256)
	p.add_argument('--postprocess', '-p', action = 'store_true')
	p.add_argument('--tta', '-t', action = 'store_true')
	args = p.parse_args()

	# Load and initialize DNN model
	print('Loading vocal-splitter model ...', end = ' ', flush = True)
	device = torch.device('cpu')
	model = nets.CascadedNet(args.n_fft)
	model.load_state_dict(torch.load(args.pretrained_model, map_location = device))
	if torch.cuda.is_available() and args.gpu >= 0:
		device = torch.device('cuda:{}'.format(args.gpu))
		model.to(device)
	args.model = model
	args.device = device
	print('done')

	# Create temporary files
	in_wav, out_wav_nonvocal, out_wav_vocal = [tempfile.NamedTemporaryFile() for i in range(3)]

	# Main loop
	while True:
		split_vocal(in_wav, out_wav_nonvocal, out_wav_vocal, args)


if __name__ == '__main__':
	main()
