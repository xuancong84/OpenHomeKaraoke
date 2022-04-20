import os
import sys
from collections import *


def is_raspberry_pi():
	try:
		return os.uname()[4][:3] == "arm" and sys.platform != "darwin"
	except AttributeError:
		return False


def get_platform():
	if sys.platform == "darwin":
		return "osx"
	elif is_raspberry_pi():
		return "raspberry_pi"
	elif sys.platform.startswith("linux"):
		return "linux"
	elif sys.platform.startswith("win"):
		return "windows"
	else:
		return "unknown"


lang_popularity = defaultdict(lambda: 0, {'English': 1132, 'Simplified Chinese': 1117, 'Traditional Chinese': 1116, 'Hindi': 615, 'Spanish': 534, 'French': 280, 'Arabic': 274,
                                          'Bengali': 265, 'Russian': 258, 'Portuguese': 234, 'Indonesian': 199, 'Urdu': 170, 'German': 132, 'Japanese': 128, 'Swahili': 98,
                                          'Punjabi': 93, 'Tamil': 81, 'Turkish': 80, 'Korean': 77, 'Vietnamese': 77, 'Javanese': 68, 'Italian': 68, 'Hausa': 63, 'Thai': 61,
                                          'Gujarati': 61, 'Kannada': 56, 'Persian': 53, 'Bhojpuri': 52, 'Filipino': 45, 'Burmese': 43, 'Polish': 40, 'Yoruba': 40, 'Odia': 38,
                                          'Malayalam': 38, 'Maithili': 34, 'Ukrainian': 33, 'Sunda': 32, 'Zulu': 28, 'Igbo': 27, 'Amharic': 26, 'Uzbek': 25, 'Sindhi': 25,
                                          'Nepali': 25, 'Romanian': 24, 'Tagalog': 24, 'Dutch': 23, 'Pashto': 21, 'Magahi': 21, 'Saraiki': 20, 'Xhosa': 19, 'Malay': 19,
                                          'Khmer': 18, 'Afrikaans': 18, 'Sinhala': 17, 'Somali': 16, 'Chhattisgarhi': 16, 'Cebuano': 16, 'Assamese': 15, 'Kurdish': 15,
                                          'Bavarian': 14, 'Bamanankan': 14, 'Azerbaijani': 14, 'Setswana': 14, 'Czech': 13, 'Greek': 13, 'Chittagonian': 13, 'Kazakh': 13,
                                          'Swedish': 13, 'Deccan': 13, 'Hungarian': 13, 'Jula': 12, 'Sadri': 12, 'Kinyarwanda': 12, 'Sylheti': 12, 'Marathi': 95, 'Telugu': 93})

lang_iso_name = """
Afrikaans,af
Albanian,sq
Amharic,am
Arabic,ar
Armenian,hy
Azerbaijani,az
Basque,eu
Belarusian,be
Bengali,bn
Bosnian,bs
Bulgarian,bg
Catalan,ca
Cebuano,ceb
Simplified Chinese,zh_CN
Traditional Chinese,zh_TW
Corsican,co
Croatian,hr
Czech,cs
Danish,da
Dutch,nl
English,en
Esperanto,eo
Estonian,et
Finnish,fi
French,fr
Frisian,fy
Galician,gl
Georgian,ka
German,de
Greek,el
Gujarati,gu
Haitian Creole,ht
Hausa,ha
Hawaiian,haw
Hebrew,he
Hindi,hi
Hmong,hmn
Hungarian,hu
Icelandic,is
Igbo,ig
Indonesian,id
Irish,ga
Italian,it
Japanese,ja
Javanese,jw
Kannada,kn
Kazakh,kk
Khmer,km
Kinyarwanda,rw
Korean,ko
Kurdish,ku
Kyrgyz,ky
Lao,lo
Latvian,lv
Lithuanian,lt
Luxembourgish,lb
Macedonian,mk
Malagasy,mg
Malay,ms
Malayalam,ml
Maltese,mt
Maori,mi
Marathi,mr
Mongolian,mn
Myanmar,my
Nepali,ne
Norwegian,no
Nyanja,ny
Odia,or
Pashto,ps
Persian,fa
Polish,pl
Portuguese,pt
Punjabi,pa
Romanian,ro
Russian,ru
Samoan,sm
Scots Gaelic,gd
Serbian,sr
Sesotho,st
Shona,sn
Sindhi,sd
Sinhala,si
Slovak,sk
Slovenian,sl
Somali,so
Spanish,es
Sundanese,su
Swahili,sw
Swedish,sv
Tagalog,tl
Tajik,tg
Tamil,ta
Tatar,tt
Telugu,te
Thai,th
Turkish,tr
Turkmen,tk
Ukrainian,uk
Urdu,ur
Uyghur,ug
Uzbek,uz
Vietnamese,vi
Welsh,cy
Xhosa,xh
Yiddish,yi
Yoruba,yo
Zulu,zu
"""


def find_language(lang):
	check_lang = lambda L: L if L in os.langs else None
	lang = lang.replace('-', '_')
	found = check_lang(lang)
	if not found:
		prefix = lang.split("_")[0]
		found = check_lang(prefix)
	if not found:
		for k in sorted(os.langs.keys()):
			if k.startswith(prefix):
				found = check_lang(k)
	if not found:
		found = check_lang('en_US')
	return found


def set_language(lang):
	if not hasattr(os, 'langs'):
		iso2name = {p[1]: p[0] for L in lang_iso_name.strip().splitlines() for p in [L.strip().split(',')]}
		iso2popularity = defaultdict(lambda: 0, {k: lang_popularity[v] for k, v in iso2name.items()})
		loadf = lambda f: defaultdict(lambda: "", {ii: L for ii, L in enumerate([''] + open(f, 'rb').read().decode('utf-8', 'ignore').splitlines())})
		sorted_lang_list = sorted(os.listdir('lang'), key = lambda t: iso2popularity.get(t, iso2popularity[t.split('_')[0]]), reverse=True)
		os.langs = {f: loadf('lang/' + f) for f in sorted_lang_list if os.path.getsize('lang/' + f) and not f.startswith('.')}
	new_lang = find_language(lang)
	if not new_lang:
		raise Exception(f"Language file lang/{lang} not found")
	os.lang = new_lang
	os.texts = os.langs[new_lang]
