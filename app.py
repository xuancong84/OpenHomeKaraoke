#!/usr/bin/env python3

import argparse, datetime, json, locale, os, sys, io, shutil
import subprocess, threading, time, traceback, webbrowser
from functools import wraps

import psutil, tempfile
from unidecode import unidecode
from flask import *
from flask.logging import logging
from pydub import AudioSegment as AudSeg
from flask_sock import Sock
from flask_paginate import Pagination, get_page_parameter

from karaoke import *
from constants import VERSION
from collections import defaultdict
from lib.get_platform import *
from lib.vlcclient import get_default_vlc_path

try:
	from urllib.parse import quote, unquote
except ImportError:
	from urllib import quote, unquote

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True	##DEBUG
app.secret_key = os.urandom(24)
admin_password = K = args = None
sock = Sock(app)
os.texts = defaultdict(lambda: "")
getString = lambda ii: os.texts[ii]
getString1 = lambda lang, ii: os.langs[lang].get(ii, os.langs['en_US'][ii])
getString2 = lambda ii: getString1(request.client_lang, ii)


# Websocket handler
@sock.route('/ws_init')
def ws_init(sock):
	key = sock.sock.getpeername()[0]
	ip2websock[key] = sock
	while sock.connected:
		try:
			cmd = sock.receive()
			wscmd(key, cmd)
		except:
			traceback.print_exc()
	ip2websock.pop(key)

def wscmd(client_ip, cmd):
	if cmd.startswith('pop_from_queue '):
		name = cmd.split(' ', 1)[1]
		K.queue_edit(name, 'delete')
	elif cmd.startswith('addsongs '):
		lst = cmd[9:].split('\t')
		for fn in lst[1:]:
			K.enqueue(fn, lst[0])

def status_thread():
	cached_status = ''
	while True:
		K.event_dirty.wait(1)

		status = nowplaying(False)
		if not status: continue

		status_full = json.dumps(status)
		status.pop('seektrack_value', None)
		status_str = json.dumps(status)
		if status_str != cached_status:
			K.status_dirty = True
			cached_status = status_str

		if not K.status_dirty:
			if not K.is_file_playing():
				continue
			tm = K.get_state().get('time', None)
			if tm is None:
				continue
			for ip, ws in ip2websock.items():
				if ip2pane.get(ip, '') == 'home':
					ws.send(f"seektrack.value={tm};$('#seektrack-val').text(getHHMMSS({tm}));")
			continue

		for ip, ws in ip2websock.items():
			if ip2pane.get(ip, '') == 'home':
				ws.send(f"update('{status_full}')")
			elif ip2pane.get(ip, '') == 'queue':
				ws.send(f"update('{K.queue_json}')")
		K.status_dirty = False

# Define global symbols for Jinja templates 
@app.context_processor
def inject_stage_and_region():
	return {'getString': getString, 'getString1': getString}


@app.before_request
def preprocessor():
	client_lang = request.cookies.get('lang', None)
	if client_lang is None:
		lang_str = request.cookies.get('Accept-Language', os.lang)
		for k in [j for i in lang_str.split(';') for j in i.split(',')]:
			client_lang = find_language(k)
			if client_lang is not None:
				break
	request.client_lang = find_language(client_lang or os.lang)


def filename_from_path(file_path, remove_youtube_id = True):
	rc = os.path.basename(file_path)
	rc = os.path.splitext(rc)[0]
	if remove_youtube_id:
		try:
			rc = rc.split("---")[0]  # removes youtube id if present
		except TypeError:
			rc = rc.split("---".encode("utf-8"))[0]
	return rc


def url_escape(filename):
	return quote(filename.encode("utf8"))


def is_admin():
	if (admin_password == None):
		return True
	if ('admin' in request.cookies):
		a = request.cookies.get("admin")
		if (a == admin_password):
			return True
	return False


@app.route("/")
def root():
	s = K.get_state()
	return render_template(
		"index.html",
		getString1 = lambda ii: getString1(request.client_lang, ii),
		show_transpose = K.use_vlc,
		transpose_value = K.now_playing_transpose,
		volume = s['volume'],
		admin = is_admin(),
		seektrack_value = s['time'],
		seektrack_max = s['length'],
		audio_delay = s['audiodelay'],
		play_speed = s['rate'],
		vocal_info = K.get_vocal_info(),
	)

@app.route("/home")
def home():
	s = K.get_state()
	return render_template(
		"home.html",
		getString1 = lambda ii: getString1(request.client_lang, ii),
		show_transpose = K.use_vlc,
		transpose_value = K.now_playing_transpose,
		volume = s['volume'],
		admin = is_admin(),
		seektrack_value = s['time'],
		seektrack_max = s['length'],
		audio_delay = s['audiodelay'],
		play_speed = s['rate'],
		vocal_info = K.get_vocal_info(),
	)
@app.route("/f_home")
def f_home():
	ip2pane[request.remote_addr] = 'home'
	s = K.get_state()
	return render_template(
		"f_home.html",
		getString1 = lambda ii: getString1(request.client_lang, ii),
		show_transpose = K.use_vlc,
		transpose_value = K.now_playing_transpose,
		volume = s['volume'],
		admin = is_admin(),
		seektrack_value = s['time'],
		seektrack_max = s['length'],
		audio_delay = s['audiodelay'],
		play_speed = s['rate'],
		vocal_info = K.get_vocal_info(),
	)


@app.route("/nowplaying")
def nowplaying(return_json=True):
	try:
		if K.switchingSong:
			return "" if return_json else {}
		next_song = K.queue[0]["title"] if K.queue else None
		next_user = K.queue[0]["user"] if K.queue else None
		s = K.get_state()
		rc = {
			"now_playing": K.now_playing,
			"now_playing_user": K.now_playing_user,
			"up_next": next_song,
			"next_user": next_user,
			"is_paused": s.get('state', 'paused') == 'paused',
			"volume": s['volume'],
			"transpose_value": K.now_playing_transpose,
			"seektrack_value": s['time'],
			"seektrack_max": s['length'],
			"audio_delay": s['audiodelay'],
			"vol_norm": K.normalize_vol,
			"play_speed": s['rate'],
			"vocal_info": K.get_vocal_info()
		}
		if K.has_subtitle:
			rc['subtitle_delay'] = s['subtitledelay']
			rc['show_subtitle'] = K.show_subtitle
		return json.dumps(rc) if return_json else rc
	except Exception as e:
		logging.error(f"Problem loading /nowplaying, pikaraoke may still be starting up: {e}\n{traceback.print_exc()}")
		return "" if return_json else {}


@app.route("/get_lang_list")
def get_lang_list():
	return json.dumps({k: v[1] for k, v in os.langs.items()}, sort_keys = False)


@app.route("/auto_username")
def auto_username():
	return f'user-{len(ip2websock)+1}'


@app.route("/change_language/<language>")
def change_language(language):
	try:
		set_language(language)
	except:
		logging.error(f"Failed to set server language to {language}")
	return os.lang


@app.route("/auth", methods = ["POST"])
def auth():
	d = request.form.to_dict()
	p = d["admin-password"]
	if (p == admin_password):
		resp = make_response(redirect('/'))
		expire_date = datetime.datetime.now()
		expire_date = expire_date + datetime.timedelta(days = 90)
		resp.set_cookie('admin', admin_password, expires = expire_date)
		flash(getString(1), "is-success")
	else:
		resp = make_response(redirect(url_for('login')))
		flash(getString(2), "is-danger")
	return resp


@app.route("/login")
def login():
	return render_template("login.html")


@app.route("/logout")
def logout():
	resp = make_response(redirect('/'))
	resp.set_cookie('admin', '')
	flash(getString(3), "is-success")
	return resp


@app.route("/user_rename/<old_name>/<new_name>")
def user_rename(old_name, new_name):
	dirty = False
	for q in K.queue:
		if q['user'] == old_name:
			q['user'] = new_name
			dirty = True
	if dirty:
		K.update_queue()
	return ''


@app.route("/get_vocal_todo_list/<vocal_device>/")
@app.route("/get_vocal_todo_list/<vocal_device>/<path:last_completed>")
def get_vocal_todo_list(vocal_device, last_completed=''):
	K.vocal_device = vocal_device
	if last_completed in K.rename_history:
		K.rename(last_completed, os.path.splitext(K.rename_history[last_completed])[0])
		K.rename_history.pop(last_completed)
	q = ([K.now_playing_filename] if K.now_playing_filename else []) + [i['file'] for i in K.queue]
	return json.dumps({'download_path': K.download_path, 'queue': q, 'use_DNN': K.use_DNN_vocal})


@app.route("/save_delays/<state>")
def set_save_delays(state):
	K.set_save_delays(state.lower() == 'true')
	return ''


@app.route("/set_vocal_mode/<mode>")
def set_vocal_mode(mode):
	K.use_DNN_vocal = (mode.lower() == 'true')
	K.play_vocal()
	return ''


@app.route("/norm_vol/<mode>", methods = ["GET"])
def norm_vol(mode):
	K.enable_vol_norm(mode.lower() == 'true')
	return ''


@app.route("/queue")
def queue():
	return render_template("queue.html", getString1 = lambda ii: getString1(request.client_lang, ii), queue = K.queue, admin = is_admin())
@app.route("/f_queue")
def f_queue():
	ip2pane[request.remote_addr] = 'queue'
	return render_template("f_queue.html", getString1 = lambda ii: getString1(request.client_lang, ii), queue = K.queue, admin = is_admin())


@app.route("/get_queue", methods = ["GET"])
def get_queue():
	return K.queue_json


@app.route("/queue/addrandom", methods = ["GET"])
def add_random():
	amount = int(request.args["amount"])
	rc = K.queue_add_random(amount)
	if rc:
		flash(getString(4) % amount, "is-success")
	else:
		flash(getString(5), "is-warning")
	return ''


@app.route("/queue/edit", methods = ["GET"])
def queue_edit():
	action = request.args["action"]
	if action == "clear":
		K.queue_clear()
		flash(getString(6), "is-warning")
		return redirect(url_for("queue"))
	elif action == "move":
		try:
			id_from = request.args['from']
			id_to = request.args['to']
			id_size = request.args['size']
		except:
			flash(getString(7))

		result = K.queue_edit(None, "move", src=id_from, tgt=id_to, size=id_size)
		if result:
			flash(f"{getString(8)} {id_from}->{id_to}/{id_size}")
		else:
			flash(f"{getString(9)} {id_from}->{id_to}/{id_size}")
	else:
		song = request.args["song"]
		song = unquote(song)
		if action == "down":
			result = K.queue_edit(song, "down")
			if result:
				flash(getString(10) + song, "is-success")
			else:
				flash(getString(11) + song, "is-danger")
		elif action == "up":
			result = K.queue_edit(song, "up")
			if result:
				flash(getString(12) + song, "is-success")
			else:
				flash(getString(13) + song, "is-danger")
		elif action == "delete":
			result = K.queue_edit(song, "delete")
			if result:
				flash(getString(14) + song, "is-success")
			else:
				flash(getString(15) + song, "is-danger")
	return redirect(url_for("queue"))


@app.route("/enqueue", methods = ["POST", "GET"])
def enqueue():
	d = request.values.to_dict()
	song = d['song' if 'song' in d else 'song-to-add']
	user = d['user' if 'user' in d else 'song-added-by']
	rc = K.enqueue(song, user)
	song_title = filename_from_path(song)
	return json.dumps({"song": song_title, "success": rc})


@app.route("/skip")
def skip():
	K.skip()
	return ''


@app.route("/pause")
def pause():
	K.pause()
	return json.dumps(K.is_paused)


@app.route("/transpose/<semitones>", methods = ["GET"])
def transpose(semitones):
	K.play_transposed(semitones)
	return ''


@app.route("/play_vocal/<mode>", methods = ["GET"])
def play_vocal(mode):
	K.play_vocal(mode)
	return ''


@app.route("/play_speed/<speed>", methods = ["GET"])
def play_speed(speed):
	K.play_speed_set(speed)
	return ''


@app.route("/seek/<goto_sec>", methods = ["GET"])
def seek(goto_sec):
	K.seek(goto_sec)
	return ''


@app.route("/audio_delay/<delay_val>", methods = ["GET"])
def audio_delay(delay_val):
	res = K.set_audio_delay(delay_val)
	return json.dumps(res)


@app.route("/subtitle_delay/<delay_val>", methods = ["GET"])
def subtitle_delay(delay_val):
	res = K.set_subtitle_delay(delay_val)
	return json.dumps(res)


@app.route("/toggle_subtitle")
def toggle_subtitle():
	K.toggle_subtitle()
	return ''


@app.route("/restart")
def restart():
	K.restart()
	return redirect(url_for("home"))


@app.route("/vol_up")
def vol_up():
	return str(K.vol_up())


@app.route("/vol_down")
def vol_down():
	return str(K.vol_down())


@app.route("/vol/<volume>")
def vol_set(volume):
	return str(K.vol_set(volume))


@app.route("/search", methods = ["GET"])
def search():
	if "search_string" in request.args:
		search_string = request.args["search_string"]
		search_karaoke = request.args.get('non_karaoke', 'false') == "true"
		search_results = K.get_search_results(search_string + (" karaoke" if search_karaoke else ""))
	else:
		search_string = None
		search_results = None
		search_karaoke = False
	return render_template(
		"search.html",
		getString1 = lambda ii: getString1(request.client_lang, ii),
		songs = K.available_songs,
		high_quality = K.high_quality,
		search_results = search_results,
		search_string = search_string,
		search_karaoke = search_karaoke
	)
@app.route("/f_search", methods = ["GET", "POST"])
def f_search():
	ip2pane[request.remote_addr] = 'search'
	dct = request.values.to_dict()
	if "search_string" in dct:
		search_string = dct["search_string"]
		search_karaoke = dct.get('non_karaoke', 'false') == "true"
		search_results = K.get_search_results(search_string + (" karaoke" if search_karaoke else ""))
	else:
		search_string = ''
		search_results = None
		search_karaoke = False
	return render_template(
		"f_search.html",
		getString1 = lambda ii: getString1(request.client_lang, ii),
		songs = K.available_songs,
		high_quality = K.high_quality,
		search_results = search_results,
		search_karaoke = search_karaoke
	)


@app.route("/autocomplete")
def autocomplete():
	q = request.args.get('q').lower()
	result = []
	for each in K.available_songs:
		if q in each.lower():
			result.append({"path": each, "fileName": K.filename_from_path(each), "type": "autocomplete"})
	response = app.response_class(
		response = json.dumps(result),
		mimetype = 'application/json'
	)
	return response


@app.route("/suggest")
def suggest():
	q = request.args.get('q').lower()
	res = {K.filename_from_path(s):s for s in K.available_songs if q in s.lower()}
	return json.dumps(res)


@app.route("/browse", methods = ["GET"])
def browse():
	search = bool(request.args.get('q'))
	page = request.args.get(get_page_parameter(), type = int, default = 1)

	letter = request.args.get('letter')

	available_songs = K.available_songs
	if letter:
		if (letter == "numeric"):
			available_songs = [k for k,v in K.songname_trans.items() if not v[0].islower()]
		else:
			available_songs = [k for k,v in K.songname_trans.items() if v.startswith(letter)]

	if "sort" in request.args and request.args["sort"] == "date":
		songs = sorted(available_songs, key = lambda x: os.path.getctime(x))
		songs.reverse()
		sort_order = "Date"
		sort_order_text = getString2(99)
	else:
		songs = available_songs
		sort_order = "Alphabetical"
		sort_order_text = getString2(100)

	results_per_page = 500
	pagination = Pagination(css_framework = 'bulma', page = page, total = len(songs), search = search, search_msg = getString2(103),
	                        record_name = getString2(101), display_msg = getString2(102), per_page = results_per_page)
	start_index = (page - 1) * (results_per_page - 1)
	return render_template(
		"files.html",
		getString1 = getString2,
		pagination = pagination,
		sort_order = sort_order,
		sort_order_text = sort_order_text,
		letter = letter,
		title = getString2(98),
		songs = songs[start_index:start_index + results_per_page],
		admin = is_admin()
	)
@app.route("/f_browse", methods = ["GET"])
def f_browse():
	ip2pane[request.remote_addr] = 'browse'
	search = bool(request.args.get('q'))
	page = request.args.get(get_page_parameter(), type = int, default = 1)

	letter = request.args.get('letter')

	available_songs = K.available_songs
	if letter:
		if (letter == "numeric"):
			available_songs = [k for k,v in K.songname_trans.items() if not v[0].islower()]
		else:
			available_songs = [k for k,v in K.songname_trans.items() if v.startswith(letter)]

	if request.cookies.get("sort") == "date":
		songs = sorted(available_songs, key = lambda x: os.path.getctime(x))
		songs.reverse()
		sort_order = "Date"
		sort_order_text = getString2(99)
	else:
		songs = available_songs
		sort_order = "Alphabetical"
		sort_order_text = getString2(100)

	results_per_page = 500
	pagination = Pagination(css_framework = 'bulma', page = page, total = len(songs), search = search, search_msg = getString2(103),
	                        record_name = getString2(101), display_msg = getString2(102), per_page = results_per_page)
	start_index = (page - 1) * (results_per_page - 1)
	return render_template(
		"f_browse.html",
		getString1 = getString2,
		pagination = pagination,
		sort_order = sort_order,
		sort_order_text = sort_order_text,
		letter = letter,
		title = getString2(98),
		songs = songs[start_index:start_index + results_per_page],
		admin = is_admin()
	)

def transform_boolean(dct, S):
	return {k: ((v=='on') if k in S else v) for k, v in dct.items()}

@app.route("/download", methods = ["POST"])
def download():
	dct = transform_boolean(request.form.to_dict(), {'enqueue', 'include_subtitles', 'high_quality'})

	# download in the background since this can take a few minutes
	t = threading.Thread(target = K.download_video, kwargs = dct|{'client_ip': request.remote_addr, 'client_lang': request.client_lang})
	t.daemon = True
	t.start()

	return getString(16) + dct["song_url"] + '\n' + getString(17 if dct.get('enqueue', False) else 18)

@app.route("/check_download", methods = ["POST"])
def check_download():
	ret = K.downloading_songs.get(request.values.get('url', None), 1)
	return str(ret)

@app.route("/qrcode")
def qrcode():
	return send_file(K.qr_code_path, mimetype = "image/png")

@app.route("/logo")
def logo():
	return send_file(K.logo_path, mimetype="image/png")

@app.route("/files/delete", methods = ["GET"])
def delete_file():
	if "song" in request.args:
		song_path = request.args["song"]
		if K.is_song_in_queue(song_path):
			flash(getString(19) + song_path, "is-danger")
		else:
			K.delete(song_path)
			flash(getString(20) + song_path, "is-warning")
	else:
		flash(getString(21), "is-danger")
	return redirect(url_for("browse"))


@app.route("/files/edit", methods = ["GET", "POST"])
def edit_file():
	queue_error_msg = getString(22)
	if "song" in request.args:
		song_path = request.args["song"]
		if song_path == K.now_playing_filename:
			flash(queue_error_msg + song_path, "is-danger")
			return redirect(url_for("browse"))
		else:
			return render_template("edit.html", getString1 = lambda ii: getString1(request.client_lang, ii), title = getString(23), song = song_path.encode("utf-8"))
	else:
		d = request.form.to_dict()
		if "new_file_name" in d and "old_file_name" in d:
			new_name = d["new_file_name"]
			old_name = d["old_file_name"]
			if old_name == K.now_playing_filename:
				flash(queue_error_msg + old_name, "is-danger")
			else:
				# check if new_name already exist
				file_extension = os.path.splitext(old_name)[1]
				if os.path.isfile(os.path.join(K.download_path, new_name + file_extension)):
					flash(getString(24) % (old_name, new_name + file_extension), "is-danger")
				else:
					K.rename(old_name, new_name)
					flash(getString(25) % (old_name, new_name), "is-warning")
		else:
			flash(getString(26), "is-danger")
		return redirect(url_for("browse"))

@app.route("/f_edit", methods = ["GET", "POST"])
def f_edit():
	song_path = request.args["song"]
	if song_path == K.now_playing_filename:
		flash(getString2(22) + song_path, "is-danger")
		return '', 400
	else:
		song = AudSeg.from_file(song_path)
		return render_template("f_edit.html", getString1 = lambda ii: getString1(request.client_lang, ii), dBFS = '%.2f'%song.dBFS,
			hhmmss = sec2hhmmss(song.duration_seconds), title = getString(23), song = song_path.encode("utf-8"))

@app.route("/edit_song", methods = ["POST"])
def rename():
	d = request.form
	if "new_file_name" in d and "old_file_name" in d:
		new_name = d["new_file_name"]
		old_name = d["old_file_name"]
		if old_name == K.now_playing_filename:
			flash(getString2(22) + old_name, "is-danger")
		elif new_name != old_name:
			# check if new_name already exist
			file_extension = os.path.splitext(old_name)[1]
			if os.path.isfile(os.path.join(K.download_path, new_name + file_extension)):
				flash(getString2(24) % (old_name, new_name + file_extension), "is-danger")
			else:
				K.rename(old_name, new_name)
				flash(getString2(25) % (old_name, new_name), "is-info")
				return f_browse()
	else:
		flash(getString2(220), "is-danger")
	return '', 400


@app.route("/splash")
def splash():
	return render_template(
		"splash.html",
		getString1 = lambda ii: getString1(request.client_lang, ii),
		blank_page=True,
		url=request.url_root
	)

@app.route("/info")
def info():
	url = K.url

	# cpu
	cpu = str(psutil.cpu_percent()) + "%"

	# mem
	memory = psutil.virtual_memory()
	available = round(memory.available / 1024.0 / 1024.0, 1)
	total = round(memory.total / 1024.0 / 1024.0, 1)
	memory = str(available) + "MB free / " + str(total) + "MB total ( " + str(memory.percent) + "% )"

	# disk
	disk = psutil.disk_usage("/")
	# Divide from Bytes -> KB -> MB -> GB
	free = round(disk.free / 1024.0 / 1024.0 / 1024.0, 1)
	total = round(disk.total / 1024.0 / 1024.0 / 1024.0, 1)
	disk = str(free) + "GB free / " + str(total) + "GB total ( " + str(disk.percent) + "% )"

	# whether screencapture.sh and vocal_splitter.py is running
	get_status = lambda t: getString2(27) if t is None else (getString2(28) if t else getString2(29))
	screencapture = K.streamer_alive()
	vocalsplitter = K.vocal_alive()
	vocal_extra = ''
	if vocalsplitter:
		vocal_extra = getString2(30) if K.vocal_device == 'cpu' else getString2(31)

	# youtube-dl
	youtubedl_version = K.youtubedl_version

	is_pi = get_platform() == "raspberry_pi"

	return render_template(
		"info.html",
		getString1 = getString2,
		langs = os.langs, lang = os.lang,
		ostype = sys.platform.upper(),
		url = url,
		memory = memory,
		cpu = cpu,
		disk = disk,
		youtubedl_version = youtubedl_version,
		is_pi = is_pi,
		use_DNN = K.use_DNN_vocal,
		norm_vol = K.normalize_vol,
		pikaraoke_version = VERSION,
		download_path = K.download_path,
		num_of_songs = len(K.available_songs),
		screencapture = get_status(screencapture),
		vocalsplitter = get_status(vocalsplitter) + vocal_extra,
		platform = K.platform,
		save_delays = bool(K.save_delays),
		admin = is_admin(),
		admin_enabled = admin_password != None
	)
@app.route("/f_info")
def f_info():
	url = K.url

	# cpu
	cpu = str(psutil.cpu_percent()) + "%"

	# mem
	memory = psutil.virtual_memory()
	available = round(memory.available / 1024.0 / 1024.0, 1)
	total = round(memory.total / 1024.0 / 1024.0, 1)
	memory = str(available) + "MB free / " + str(total) + "MB total ( " + str(memory.percent) + "% )"

	# disk
	disk = psutil.disk_usage("/")
	# Divide from Bytes -> KB -> MB -> GB
	free = round(disk.free / 1024.0 / 1024.0 / 1024.0, 1)
	total = round(disk.total / 1024.0 / 1024.0 / 1024.0, 1)
	disk = str(free) + "GB free / " + str(total) + "GB total ( " + str(disk.percent) + "% )"

	# whether screencapture.sh and vocal_splitter.py is running
	get_status = lambda t: getString2(27) if t is None else (getString2(28) if t else getString2(29))
	screencapture = K.streamer_alive()
	vocalsplitter = K.vocal_alive()
	vocal_extra = ''
	if vocalsplitter:
		vocal_extra = getString2(30) if K.vocal_device == 'cpu' else getString2(31)

	# youtube-dl
	youtubedl_version = K.youtubedl_version

	is_pi = get_platform() == "raspberry_pi"

	return render_template(
		"f_info.html",
		getString1 = getString2,
		langs = os.langs, lang = os.lang,
		ostype = sys.platform.upper(),
		url = url,
		memory = memory,
		cpu = cpu,
		disk = disk,
		youtubedl_version = youtubedl_version,
		is_pi = is_pi,
		use_DNN = K.use_DNN_vocal,
		norm_vol = K.normalize_vol,
		pikaraoke_version = VERSION,
		download_path = K.download_path,
		num_of_songs = len(K.available_songs),
		screencapture = get_status(screencapture),
		vocalsplitter = get_status(vocalsplitter) + vocal_extra,
		platform = K.platform,
		save_delays = bool(K.save_delays),
		admin = is_admin(),
		admin_enabled = admin_password != None
	)

def run_asr():
	global args
	with open(f'{K.tmp_dir}/rec.webm', 'rb') as f:
		r = requests.post(args.cloud+'/run_asr/base', files={'file': f}, timeout=8)
	asr_output = json.loads(r.text) if r.status_code==200 else {}
	return asr_output

def _add_spoken(client_ip, user, getString):
	asr_output = run_asr()

	print(f'ASR result: {asr_output}', file=sys.stderr)
	if asr_output=={} or type(asr_output)==str:
		return logging.error(f'Cloud ASR returns HTTP status code = {r.status_code} ()')
	elif not asr_output['text']:
		return logging.error(f'ASR output is empty')

	res = findMedia(K.download_path, asr_output['text'], lang=asr_output['language'])
	ws = ip2websock.get(client_ip, '')
	if not res:
		return ws.send(f"showNotification('{getString(226)%asr_output['text']}', 'is-info')")
	res_titles = [filename_from_path(s) for s in res]
	if len(res)==1:
		add_res = K.enqueue(res[0], user)
		return ws.send(f'add1song("{res_titles[0]}","{res[0]}")' if add_res else f"showNotification('{getString(116)+res_titles[0]}', 'is-info')")
	return ws.send(f"addSongs('{json.dumps([res_titles, res])}')")


@app.route('/add_spoken/<user>', methods=['POST'])
def add_spoken(user):
	with open(f'{K.tmp_dir}/rec.webm', 'wb') as fp:
		fp.write(request.data)
	threading.Thread(target=_add_spoken, args=(request.remote_addr, user, getString)).start()
	return 'OK'

@app.route('/get_ASR', methods=['POST'])
@app.route('/get_ASR/<path:cmd>', methods=['POST'])
def get_ASR(cmd=''):
	with open(f'{K.tmp_dir}/rec.webm', 'wb') as fp:
		fp.write(request.data)
	asr_output = run_asr()
	return asr_output['text']


# Delay system commands to allow redirect to render first
def delayed_halt(cmd):
	time.sleep(3)
	if K.vocal_process is not None and K.vocal_process.is_alive():
		K.vocal_process.terminate()
	K.queue_clear()  # stop all pending omxplayer processes
	K.stop()
	if cmd == 0:
		os.system('(sleep 2 && tmux kill-session -t PiKaraoke) &')
		sys.exit()
	if cmd == 1:
		os.system("shutdown now")
	if cmd == 2:
		os.system("reboot")
	if cmd == 3:
		process = subprocess.Popen(["raspi-config", "--expand-rootfs"])
		process.wait()
		os.system("reboot")


@app.route("/refresh")
def refresh():
	if (is_admin()):
		K.get_available_songs()
	else:
		flash(getString(34), "is-danger")
	return redirect(url_for("browse"))


@app.route("/bg-process/<cmd>")
def bg_process(cmd):
	if cmd == 'streamer-restart':
		K.streamer_restart()
	elif cmd == 'streamer-stop':
		K.streamer_stop()
	elif cmd == 'vocal-restart':
		K.vocal_restart()
	elif cmd == 'vocal-stop':
		K.vocal_stop()
	return ''


@app.route("/quit")
def quit():
	if (is_admin()):
		flash(getString(35), "is-warning")
		threading.Thread(target = delayed_halt, args = [0]).start()
	else:
		flash(getString(36), "is-danger") 
	return ''


@app.route("/shutdown")
def shutdown():
	if (is_admin()):
		flash(getString(37), "is-danger")
		threading.Thread(target = delayed_halt, args = [1]).start()
	else:
		flash(getString(38), "is-danger")
	return ''


@app.route("/reboot")
def reboot():
	if (is_admin()):
		flash(getString(39), "is-danger")
		threading.Thread(target = delayed_halt, args = [2]).start()
	else:
		flash(getString(40), "is-danger")
	return ''


@app.route("/update_ytdl")
def update_ytdl():
	if (is_admin()):
		flash(getString(32), "is-warning")
		threading.Thread(target=lambda: K.upgrade_youtubedl()).start()
	else:
		flash(getString(33), "is-danger")
	return ''


@app.route("/expand_fs")
def expand_fs():
	if (is_admin() and platform == "raspberry_pi"):
		flash(getString(41), "is-danger")
		threading.Thread(target = delayed_halt, args = [3]).start()
	elif (platform != "raspberry_pi"):
		flash(getString(42), "is-danger")
	else:
		flash(getString(43), "is-danger")
	return ''


def get_default_dl_dir():
	return os.path.expanduser("~/pikaraoke-songs")

def get_default_tmp_dir():
	return '/dev/shm' if os.path.isdir('/dev/shm') else tempfile.gettempdir()

def get_default_browser_cookie(platform):
	platform = 'linux' if platform=='raspberry_pi' else platform
	def_cookie_loc = defaultdict(lambda:defaultdict(lambda:''))
	def_cookie_loc['linux']['firefox'] = '$HOME/.mozilla/firefox/'
	def_cookie_loc['linux']['chrome'] = '$HOME/.config/google-chrome/'
	def_cookie_loc['linux']['chromium'] = '$HOME/.config/chromium/'
	def_cookie_loc['windows']['firefox'] = '%APPDATA%\\Mozilla\\Firefox\\Profiles'
	def_cookie_loc['windows']['chrome'] = '%LOCALAPPDATA%\\Google\\Chrome\\User Data\\Default\\Network'
	def_cookie_loc['windows']['edge'] = '%LOCALAPPDATA%\\Microsoft\\Edge\\User Data\\Default\\Network'
	def_cookie_loc['windows']['ie'] = '%USERPROFILE%\\AppData\\Roaming\\Microsoft\\Windows\\Cookies'
	def_cookie_loc['osx']['firefox'] = '$HOME/Library/Application Support/Firefox/Profiles/'
	def_cookie_loc['osx']['chrome'] = '$HOME/Library/Application Support/Google/Chrome/'
	def_cookie_loc['osx']['safari'] = '$HOME/Library/Cookies/'
	try:
		if platform == 'windows':
			browsers = ['firefox', 'chrome', 'ie', 'edge']
			from winreg import OpenKey, HKEY_CURRENT_USER, QueryValueEx
			with OpenKey(HKEY_CURRENT_USER,
						 r"Software\\Microsoft\\Windows\\Shell\\Associations\\UrlAssociations\\http\\UserChoice") as key:
				browser = QueryValueEx(key, 'Progid')[0].lower()
			default_browser = [b for b in browsers if browser.startswith(b)][0]
		else:
			default_browser = webbrowser.get().name.lower()
	except:
		return ''
	ret = os.path.expandvars(def_cookie_loc[platform][default_browser])
	return f'{default_browser}:{ret}' if ret else ''


if __name__ == "__main__":
	platform = get_platform()
	default_port = 5000
	default_volume = 0
	default_splash_delay = 3
	default_log_level = logging.INFO

	default_dl_dir = get_default_dl_dir()
	default_omxplayer_path = "/usr/bin/omxplayer"
	default_adev = "both"
	default_vlc_path = get_default_vlc_path(platform)
	default_vlc_port = 5002

	# parse CLI args
	parser = argparse.ArgumentParser()

	parser.add_argument(
		"-p", "--port", type=int,
		help = f"Desired http/https port (default: {default_port})",
		default = default_port,
	)
	parser.add_argument(
		"-d", "--download-path",
		help = f"Desired path for downloaded songs. (default: {default_dl_dir})",
		default = default_dl_dir,
	)
	parser.add_argument(
		"-sd", "--save-delays",
		help = f"Filename for saving subtitle/audio/etc. delays for each song, can be: 1. auto(default): if <download-path>/.delays exist, then enable; 2. yes: save; 3. no: do not save; 4. <filename>: specific file for storing the delays",
		default = 'auto',
	)
	parser.add_argument(
		"-o", "--omxplayer-path",
		help = f"Path of omxplayer. Only important to raspberry pi hardware. (default: {default_omxplayer_path})",
		default = default_omxplayer_path,
	)
	parser.add_argument(
		"-y", "--youtubedl-path",
		help = f"Path of youtube-dl. (default: '', use pip package yt-dlp)",
		default = '',
	)
	parser.add_argument(
		"-v", "--volume",
		help = f"If using omxplayer, the initial player volume is specified in millibels. Negative values ok. (default: {default_volume} , Note: 100 millibels = 1 decibel).",
		default = default_volume,
	)
	parser.add_argument(
		"-V", "--run-vocal",
		help = "Explicitly run vocal-splitter process from the main program (by default, it only run explicitly in Windows)",
		action = 'store_true',
	)
	parser.add_argument(
		"-nv", "--normalize-vol",
		help = "Enable volume normalization",
		action = 'store_true',
	)
	parser.add_argument(
		"-s", "--splash-delay",
		help = f"Delay during splash screen between songs (in secs). (default: {default_splash_delay} )",
		type = float,
		default = default_splash_delay,
	)
	parser.add_argument(
		"-L", "--lang",
		help = f"Set display language (default: None, set according to the current system locale {locale.getdefaultlocale()[0]})",
		default = locale.getdefaultlocale()[0],
	)
	parser.add_argument(
		"-l", "--log-level",
		help = f"Logging level int value (DEBUG: 10, INFO: 20, WARNING: 30, ERROR: 40, CRITICAL: 50). (default: {default_log_level} )",
		default = default_log_level,
	)
	parser.add_argument(
		"--hide-ip",
		action = "store_true",
		help = "Hide IP address from the screen.",
	)
	parser.add_argument(
		"--hide-raspiwifi-instructions",
		action = "store_true",
		help = "Hide RaspiWiFi setup instructions from the splash screen.",
	)
	parser.add_argument(
		"--hide-splash-screen",
		action = "store_true",
		help = "Hide splash screen before/between songs.",
	)
	parser.add_argument(
		"--adev",
		help = f"Pass the audio output device argument to omxplayer. Possible values: hdmi/local/both/alsa[:device]."
		       f" If you are using a rpi USB soundcard or Hifi audio hat, try: 'alsa:hw:0,0' Default: '{default_adev}'",
		default = default_adev,
	)
	parser.add_argument(
		"--dual-screen",
		action = "store_true",
		help = "Output video to both HDMI ports (raspberry pi 4 only)",
	)
	parser.add_argument(
		"--high-quality", "-hq",
		action = "store_true",
		help = "Download higher quality video. Note: requires ffmpeg and may cause CPU, download speed, and other performance issues",
	)
	parser.add_argument(
		"--use-omxplayer",
		action = "store_true",
		help = "Use OMX Player to play video instead of the default VLC Player. This may be better-performing on older raspberry pi devices."
		       " Certain features like key change and cdg support wont be available. Note: if you want to play audio to the headphone jack on a rpi,"
		       " you'll need to configure this in raspi-config: 'Advanced Options > Audio > Force 3.5mm (headphone)'",
	)
	parser.add_argument(
		"--use-vlc",
		action = "store_true",
		help = "Use VLC Player to play video. Enabled by default. Note: if you want to play audio to the headphone jack on a rpi, see troubleshooting steps in README.md",
	)
	parser.add_argument(
		"--vlc-path",
		help = f"Full path to VLC (Default: {default_vlc_path})",
		default = default_vlc_path,
	)
	parser.add_argument(
		"--vlc-port",
		help = f"HTTP port for VLC remote control api (Default: {default_vlc_port})",
		default = default_vlc_port,
	)
	parser.add_argument(
		"--logo-path",
		help = "Path to a custom logo image file for the splash screen. Recommended dimensions ~ 500x500px",
		default = None,
	)
	parser.add_argument(
		"--show-overlay",
		action = "store_true",
		help = "Show overlay on top of video with pikaraoke QR code and IP",
	)
	parser.add_argument(
		'-w', "--windowed",
		action = "store_true",
		help = "Start PiKaraoke in windowed mode",
	)
	parser.add_argument(
		'-c', "--browser-cookies",
		default = "auto",
		help = "YouTube downloader can use browser cookies from the specified path (see the --cookies-from-browser option of yt-dlp), it can also be auto (default): automatically determine based on OS; none: do not use any browser cookies",
	)
	parser.add_argument(
		"--admin-password",
		help = "Administrator password, for locking down certain features of the web UI such as queue editing, player controls, song editing, and system shutdown. If unspecified, everyone is an admin.",
		default = None,
	)
	parser.add_argument(
		"--ssl", "-ssl",
		help = "Use HTTPS instead of HTTP (browser microphone access requires HTTPS)",
		action = 'store_true'
	)
	parser.add_argument(
		"--temp", "-tp",
		default = None,
		help = "Temporary folder location",
	)
	parser.add_argument(
		'--cloud', '-C',
		default='',
		help='cloud URL for DNN-based vocal split and speech recognition',
	)
	args = parser.parse_args()

	set_language(args.lang)

	if (args.admin_password):
		admin_password = args.admin_password

	app.jinja_env.globals.update(filename_from_path = filename_from_path)
	app.jinja_env.globals.update(url_escape = quote)

	args.tmp_dir = os.path.expanduser(args.temp or get_default_tmp_dir())
	args.cloud = args.cloud.rstrip('/')

	# Set browser cookies location for YouTube downloader
	if args.browser_cookies.lower() == 'none':
		args.cookies_opt = []
	elif args.browser_cookies.lower() == 'auto':
		path = get_default_browser_cookie(platform)
		args.cookies_opt = ['--cookies-from-browser', path] if path else []
	else:
		args.cookies_opt = ['--cookies-from-browser', args.browser_cookies]

	# Handle OMX player if specified
	if platform == "raspberry_pi" and args.use_omxplayer:
		args.use_vlc = False
	else:
		args.use_vlc = True

	# check if required binaries exist, auto pip install yt-dlp if needed
	if not os.path.isfile(args.youtubedl_path):
		args.youtubedl_path = ''
		try:
			import yt_dlp
		except:
			try:
				import pip
				pip.main(['install', 'yt-dlp'])
			except:
				print(getString(44) + args.youtubedl_path)
				sys.exit(1)
	if args.use_vlc and not os.path.isfile(args.vlc_path):
		print(getString(45) + args.vlc_path)
		sys.exit(1)
	if platform == "raspberry_pi" and not args.use_vlc and not os.path.isfile(args.omxplayer_path):
		print(getString(46) + args.omxplayer_path)
		sys.exit(1)

	# setup/create download directory if necessary
	args.dl_path = os.path.expanduser(args.download_path).rstrip('/')+'/'
	if platform == 'windows':	# on Windows, VLC cannot open filenames containing '/'
		args.dl_path = escape_win_filename(args.dl_path)
	if not os.path.exists(args.dl_path):
		print(getString(47) + args.dl_path)
		os.makedirs(args.dl_path)

	# determine whether to save/load delays
	args.dft_delays_file = args.dl_path+'.delays'
	if args.save_delays == 'auto':
		args.save_delays = args.dft_delays_file if os.path.exists(args.dft_delays_file) else None
	elif args.save_delays == 'yes':
		args.save_delays = args.dft_delays_file
	elif args.save_delays == 'no':
		args.save_delays = None

	# Configure karaoke process
	os.K = K = Karaoke(args)

	if not args.ssl:
		threading.Thread(target=lambda:app.run(host='0.0.0.0', port=args.port+1, threaded = True, ssl_context=('cert.pem', 'key.pem'))).start()
	threading.Thread(target=lambda:app.run(host='0.0.0.0', port=args.port, threaded = True, ssl_context=('cert.pem', 'key.pem') if args.ssl else None)).start()

	threading.Thread(target=status_thread).start()

	K.run()
	os._exit(0)	# force-stop all flask threads and exit
