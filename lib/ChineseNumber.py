from typing import Union
from warnings import warn

NUMBER_CN2AN = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "壹": 1,
    "幺": 1,
    "二": 2,
    "贰": 2,
    "两": 2,
    "三": 3,
    "叁": 3,
    "四": 4,
    "肆": 4,
    "五": 5,
    "伍": 5,
    "六": 6,
    "陆": 6,
    "七": 7,
    "柒": 7,
    "八": 8,
    "捌": 8,
    "九": 9,
    "玖": 9,
}
UNIT_CN2AN = {
    "十": 10,
    "拾": 10,
    "百": 100,
    "佰": 100,
    "千": 1000,
    "仟": 1000,
    "万": 10000,
    "亿": 100000000,
}
UNIT_LOW_AN2CN = {
    10: "十",
    100: "百",
    1000: "千",
    10000: "万",
    100000000: "亿",
}
NUMBER_LOW_AN2CN = {
    0: "零",
    1: "一",
    2: "二",
    3: "三",
    4: "四",
    5: "五",
    6: "六",
    7: "七",
    8: "八",
    9: "九",
}
NUMBER_UP_AN2CN = {
    0: "零",
    1: "壹",
    2: "贰",
    3: "叁",
    4: "肆",
    5: "伍",
    6: "陆",
    7: "柒",
    8: "捌",
    9: "玖",
}
UNIT_LOW_ORDER_AN2CN = [
    "",
    "十",
    "百",
    "千",
    "万",
    "十",
    "百",
    "千",
    "亿",
    "十",
    "百",
    "千",
    "万",
    "十",
    "百",
    "千",
]
UNIT_UP_ORDER_AN2CN = [
    "",
    "拾",
    "佰",
    "仟",
    "万",
    "拾",
    "佰",
    "仟",
    "亿",
    "拾",
    "佰",
    "仟",
    "万",
    "拾",
    "佰",
    "仟",
]
STRICT_CN_NUMBER = {
    "零": "零",
    "一": "一壹",
    "二": "二贰",
    "三": "三叁",
    "四": "四肆",
    "五": "五伍",
    "六": "六陆",
    "七": "七柒",
    "八": "八捌",
    "九": "九玖",
    "十": "十拾",
    "百": "百佰",
    "千": "千仟",
    "万": "万",
    "亿": "亿",
}
NORMAL_CN_NUMBER = {
    "零": "零〇",
    "一": "一壹幺",
    "二": "二贰两",
    "三": "三叁仨",
    "四": "四肆",
    "五": "五伍",
    "六": "六陆",
    "七": "七柒",
    "八": "八捌",
    "九": "九玖",
    "十": "十拾",
    "百": "百佰",
    "千": "千仟",
    "万": "万",
    "亿": "亿",
}

class An2Cn(object):
	all_num = "0123456789"
	def __init__(self) -> None:
		self.number_low = NUMBER_LOW_AN2CN
		self.number_up = NUMBER_UP_AN2CN
		self.mode_list = ["low", "up", "rmb", "direct"]

	def an2cn(self, inputs: Union[str, int, float] = None, mode: str = "low") -> str:
		"""阿拉伯数字转中文数字

		:param inputs: 阿拉伯数字
		:param mode: low 小写数字，up 大写数字，rmb 人民币大写，direct 直接转化
		:return: 中文数字
		"""
		if inputs is not None and inputs != "":
			if mode not in self.mode_list:
				raise ValueError(f"mode 仅支持 {str(self.mode_list)} ！")

			# 将数字转化为字符串，这里会有Python会自动做转化
			# 1. -> 1.0 1.00 -> 1.0 -0 -> 0
			if not isinstance(inputs, str):
				inputs = self.__number_to_string(inputs)

			# 检查数据是否有效
			self.__check_inputs_is_valid(inputs)

			# 判断正负
			if inputs[0] == "-":
				sign = "负"
				inputs = inputs[1:]
			else:
				sign = ""

			if mode == "direct":
				output = self.__direct_convert(inputs)
			else:
				# 切割整数部分和小数部分
				split_result = inputs.split(".")
				len_split_result = len(split_result)
				if len_split_result == 1:
					# 不包含小数的输入
					integer_data = split_result[0]
					if mode == "rmb":
						output = self.__integer_convert(integer_data, "up") + "元整"
					else:
						output = self.__integer_convert(integer_data, mode)
				elif len_split_result == 2:
					# 包含小数的输入
					integer_data, decimal_data = split_result
					if mode == "rmb":
						int_data = self.__integer_convert(integer_data, "up")
						dec_data = self.__decimal_convert(decimal_data, "up")
						len_dec_data = len(dec_data)

						if len_dec_data == 0:
							output = int_data + "元整"
						elif len_dec_data == 1:
							raise ValueError(f"异常输出：{dec_data}")
						elif len_dec_data == 2:
							if dec_data[1] != "零":
								if int_data == "零":
									output = dec_data[1] + "角"
								else:
									output = int_data + "元" + dec_data[1] + "角"
							else:
								output = int_data + "元整"
						else:
							if dec_data[1] != "零":
								if dec_data[2] != "零":
									if int_data == "零":
										output = dec_data[1] + "角" + dec_data[2] + "分"
									else:
										output = int_data + "元" + dec_data[1] + "角" + dec_data[2] + "分"
								else:
									if int_data == "零":
										output = dec_data[1] + "角"
									else:
										output = int_data + "元" + dec_data[1] + "角"
							else:
								if dec_data[2] != "零":
									if int_data == "零":
										output = dec_data[2] + "分"
									else:
										output = int_data + "元" + "零" + dec_data[2] + "分"
								else:
									output = int_data + "元整"
					else:
						output = self.__integer_convert(integer_data, mode) + self.__decimal_convert(decimal_data, mode)
				else:
					raise ValueError(f"输入格式错误：{inputs}！")
		else:
			raise ValueError("输入数据为空！")

		return sign + output

	def __direct_convert(self, inputs: str) -> str:
		_output = ""
		for d in inputs:
			if d == ".":
				_output += "点"
			else:
				_output += self.number_low[int(d)]
		return _output

	@staticmethod
	def __number_to_string(number_data: Union[int, float]) -> str:
		# 小数处理：python 会自动把 0.00005 转化成 5e-05，因此 str(0.00005) != "0.00005"
		string_data = str(number_data)
		if "e" in string_data:
			string_data_list = string_data.split("e")
			string_key = string_data_list[0]
			string_value = string_data_list[1]
			if string_value[0] == "-":
				string_data = "0." + "0" * (int(string_value[1:]) - 1) + string_key
			else:
				string_data = string_key + "0" * int(string_value)
		return string_data

	def __check_inputs_is_valid(self, check_data: str) -> None:
		# 检查输入数据是否在规定的字典中
		all_check_keys = self.all_num + ".-"
		for data in check_data:
			if data not in all_check_keys:
				raise ValueError(f"输入的数据不在转化范围内：{data}！")

	def __integer_convert(self, integer_data: str, mode: str) -> str:
		if mode == "low":
			numeral_list = NUMBER_LOW_AN2CN
			unit_list = UNIT_LOW_ORDER_AN2CN
		elif mode == "up":
			numeral_list = NUMBER_UP_AN2CN
			unit_list = UNIT_UP_ORDER_AN2CN
		else:
			raise ValueError(f"error mode: {mode}")

		# 去除前面的 0，比如 007 => 7
		integer_data = str(int(integer_data))

		len_integer_data = len(integer_data)
		if len_integer_data > len(unit_list):
			raise ValueError(f"超出数据范围，最长支持 {len(unit_list)} 位")

		output_an = ""
		for i, d in enumerate(integer_data):
			if int(d):
				output_an += numeral_list[int(d)] + unit_list[len_integer_data - i - 1]
			else:
				if not (len_integer_data - i - 1) % 4:
					output_an += numeral_list[int(d)] + unit_list[len_integer_data - i - 1]

				if i > 0 and not output_an[-1] == "零":
					output_an += numeral_list[int(d)]

		output_an = output_an.replace("零零", "零").replace("零万", "万").replace("零亿", "亿").replace("亿万", "亿") \
			.strip("零")

		# 解决「一十几」问题
		if output_an[:2] in ["一十"]:
			output_an = output_an[1:]

		# 0 - 1 之间的小数
		if not output_an:
			output_an = "零"

		return output_an

	def __decimal_convert(self, decimal_data: str, o_mode: str) -> str:
		len_decimal_data = len(decimal_data)

		if len_decimal_data > 16:
			warn(f"注意：小数部分长度为 {len_decimal_data} ，将自动截取前 16 位有效精度！")
			decimal_data = decimal_data[:16]

		if len_decimal_data:
			output_an = "点"
		else:
			output_an = ""

		if o_mode == "low":
			numeral_list = NUMBER_LOW_AN2CN
		elif o_mode == "up":
			numeral_list = NUMBER_UP_AN2CN
		else:
			raise ValueError(f"error mode: {o_mode}")

		for data in decimal_data:
			output_an += numeral_list[int(data)]
		return output_an


g_An2Cn = An2Cn()
digit2low = {
	'.': "点",
	'0': "零",
	'1': "一",
	'2': "二",
	'3': "三",
	'4': "四",
	'5': "五",
	'6': "六",
	'7': "七",
	'8': "八",
	'9': "九",
}
def num2zh(txt):
	# find all numerical segments
	bm_numerical = [(c in digit2low) for c in txt]
	posi = 0
	segs = []
	while posi<len(txt):
		if bm_numerical[posi]:
			if posi:
				last = segs[-1][2] if segs else 0
				segs += [[False, last, posi, txt[last:posi]]]
			p = posi+1
			while p<len(txt) and bm_numerical[p]:
				p += 1
			seg = txt[posi:p]
			segs += [[True, posi, p, seg]]
			posi = p
		else:
			posi += 1
	segs = segs or [[False, 0, len(txt), txt]]
	if segs[-1][2]<len(txt):
		segs += [[False, segs[-1][2], len(txt), txt[segs[-1][2]:]]]
		

	# convert all segments
	out = ''
	for is_num, start, stop, seg in segs:
		if not is_num:
			out += seg
		elif seg[0] in '0.':
			out += ''.join([digit2low[c] for c in seg])
		elif len(seg)==4 and 1800<int(seg)<2100:	# year number
			out += ''.join([digit2low[c] for c in seg])
		else:
			cks = seg.split('.', 1)
			out += g_An2Cn.an2cn(cks[0])
			if len(cks)>1:
				out += ''.join([digit2low[c] for c in cks[1]])
	return out


### Convert Chinese numerals to arabic number string, e.g.
# '七百六十五万两千三百二十四' => '7652324'
# '三百八十五万点五零四二' => '3850000.5042'
# '零〇七' => '007'
fst_zh2num = {
	"〇": "零",
	"两": "二",
	"点": lambda t: t+'.',
	"零": lambda t: t+'0' if ('.' in t or set(t)=={'0'} or t=='') else t,
	"一": lambda t: t+'1' if ('.' in t or set(t)=={'0'}) else t[:-1]+'1',
	"二": lambda t: t+'2' if ('.' in t or set(t)=={'0'}) else t[:-1]+'2',
	"三": lambda t: t+'3' if ('.' in t or set(t)=={'0'}) else t[:-1]+'3',
	"四": lambda t: t+'4' if ('.' in t or set(t)=={'0'}) else t[:-1]+'4',
	"五": lambda t: t+'5' if ('.' in t or set(t)=={'0'}) else t[:-1]+'5',
	"六": lambda t: t+'6' if ('.' in t or set(t)=={'0'}) else t[:-1]+'6',
	"七": lambda t: t+'7' if ('.' in t or set(t)=={'0'}) else t[:-1]+'7',
	"八": lambda t: t+'8' if ('.' in t or set(t)=={'0'}) else t[:-1]+'8',
	"九": lambda t: t+'9' if ('.' in t or set(t)=={'0'}) else t[:-1]+'9',
	"十": lambda t: t[:-2]+(t[-1] if t else '1')+'0',
	"百": lambda t: t[:-3]+t[-1]+'00',
	"千": lambda t: t[:-4]+t[-1]+'000',
	"万": lambda t: t[:-8]+t[-4:]+'0000',
	"亿": lambda t: t[:-16]+t[-8:]+'00000000',
}

def zh2num(txt):
	out = ''
	for c in txt:
		if c not in fst_zh2num:
			return txt
		tgt = fst_zh2num[c]
		out = fst_zh2num[tgt](out) if type(tgt)==str else tgt(out)
	return out

