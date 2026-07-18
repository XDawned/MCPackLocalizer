import copy
import difflib
import hashlib
import json
import os
import re
import time
import zipfile
from collections import OrderedDict
from functools import wraps
from pathlib import Path

import func_timeout.exceptions
from openai import OpenAI
import ahocorasick
import requests
import snbtlib
from PyQt6.QtCore import QThread, pyqtSignal, QObject
from nbt import nbt
from nbt.nbt import TAG
from func_timeout import func_set_timeout

from common.config import cfg
from common.local_service import LocalInferenceClient
from common.terms_dict import TERMS

MAGIC_WORD = r'{xdawned}'  # 先在术语库中记录，保证其不被翻译


def parse_json_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        data = json.loads(f.read())
    return data


def save_file(data_, path):
    directory = os.path.dirname(path)
    if not os.path.exists(directory):
        os.makedirs(directory)
        time.sleep(0.1)
    with open(path, 'w', encoding='utf-8') as f:
        # json.dump(data_, f, indent=4, ensure_ascii=False)
        f.write(data_)


def save_lang_file(data_: dict, path: str, text: str = None):
    if path.endswith('.lang'):
        with open(path, 'w', encoding='utf-8') as f:
            for key, value in data_.items():
                value = json.dumps(value, ensure_ascii=False)
                f.write(f'{key}={value}\n')
    elif path.endswith('.json'):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data_, f, indent=1, ensure_ascii=False)
    elif path.endswith('.snbt'):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)


def func_timer(function):
    """
    用装饰器实现函数计时
    :param function: 需要计时的函数
    :return: tuple(运算的结果,运行时间)
    """

    @wraps(function)
    def function_timer(*args, **kwargs):
        t0 = time.time()
        result = function(*args, **kwargs)
        t1 = time.time()
        return result, round(t1 - t0, 2)

    return function_timer


def check_file_exists(directory_path, file_name):
    if os.path.exists(os.path.join(directory_path, file_name)):
        return directory_path + '/' + file_name
    else:
        return None


def get_if_subfolder_exists(directory, target_folder):
    target_folder_parts = target_folder.split('/')
    root_folder = target_folder_parts[0]
    sub_folders = target_folder_parts[1:]

    for root, dirs, files in os.walk(directory):
        if root.endswith(root_folder) and all(sub_folder in dirs for sub_folder in sub_folders):
            return os.path.normpath(os.path.join(root, *sub_folders))

    return None


def merge_dicts(dict1, dict2):
    merged_dict = {}

    for key, value in dict1.items():
        merged_dict[key] = value

    for key, value in dict2.items():
        if key in merged_dict:
            # 处理重叠的键
            new_key = key + "_"  # 重叠则以原有键为基础添加后缀"_"
            merged_dict[new_key] = value
        else:
            merged_dict[key] = value

    return merged_dict


def get_if_folder_exists(directory, target_folder):
    for root, dirs, files in os.walk(directory):
        if target_folder in dirs:
            return os.path.normpath(os.path.join(root, target_folder))
    return None


def encode_to_MD5(filepath:str):
    # 使用MD5进行文件内容摘要
    filepath = os.path.normpath(filepath)
    file_data = open(filepath, 'rb').read()
    mixed_file_data = bytes(filepath, encoding='utf-8') + file_data  # 防止内容相同引起的混淆
    identifier = hashlib.md5(mixed_file_data).hexdigest()
    return identifier


def find_similar_terms(term, term_dict):
    matches = difflib.get_close_matches(term, term_dict.keys(), n=50, cutoff=0.6)
    similar_terms = {match: term_dict[match] for match in matches}
    return similar_terms


class Lang:
    def __init__(self):
        self.file_path = ''
        self.lang_dic = {}
        self.cache_dic = {}
        self.cache_name = ''
        self.cache_folder = f"{cfg.get(cfg.workFolder)}/.mplt/cache"
        self.cache_file_path = ''
        self.lang_bilingual_list = []

    def read_lang(self, file_path: str):
        self.__init__()
        self.file_path = file_path
        # 读取数据
        # 兼容lang或json类型语言文件
        if file_path.endswith('.lang'):
            with open(self.file_path, 'r', encoding='utf-8') as f:
                lang_data = f.read()
                # 清理注释
                lang_data = '\n'.join(line for line in lang_data.split('\n') if not line.strip().startswith("#"))
                # 分割键值对
                lang_data = [line.strip() for line in lang_data.split('\n') if line.strip()]
                for line in lang_data:
                    key, value = line.split("=", maxsplit=1)
                    self.lang_dic[key.strip()] = value.strip()
        elif file_path.endswith('.json'):
            self.lang_dic = parse_json_file(file_path)
        self.init_cache()
        self.init_bilingual()

    def set_lang(self, data: dict, file_path: str):
        self.__init__()
        self.file_path = file_path
        self.lang_dic = data
        self.init_cache()
        self.init_bilingual()

    def init_cache(self):
        """
        初始化缓存文件
        有则加载，无则创建
        两个参数用于非Lang文件保存缓存时使用
        """
        if not self.file_path:
            raise Exception("缓存文件MD5路径生成错误,缺少文件地址")
        self.cache_name = encode_to_MD5(self.file_path) + '.json'
        self.cache_file_path = self.cache_folder + '/' + self.cache_name
        os.makedirs(self.cache_folder, exist_ok=True)
        if os.path.exists(self.cache_file_path):
            self.cache_dic = parse_json_file(self.cache_file_path)
        else:
            save_lang_file({}, self.cache_file_path)

    def init_bilingual(self):
        # 初始化双语文件，分别存放：键、原文、机翻、译文
        self.lang_bilingual_list = []
        for key, value in self.lang_dic.items():
            if self.cache_dic.get(key):
                self.lang_bilingual_list.append([key, value, self.cache_dic[key]['trans'], ''])
            else:
                self.lang_bilingual_list.append([key, value, '', ''])

    # def migrate(self, en_us_path, zh_cn_path):
    #
    #     en_us_lang = Lang()
    #     zh_cn_lang = Lang()
    #     en_us_lang.read_lang(en_us_path)
    #     zh_cn_lang.read_lang(zh_cn_path)
    #     for key, value in self.lang_dic.items():
    #         # 检查新版本中的原文是否与旧版本相同
    #         if key in old_data and old_data[key] == value:
    #             # 如果相同，将对应的翻译从旧版本语言文件迁移到新版本中
    #             updated_data[key] = old_data[key]
    #         else:
    #             # 如果不同，保留新版本中的翻译
    #             updated_data[key] = value

    def save_cache(self):
        self.cache_dic = {}
        for i in range(len(self.lang_bilingual_list)):
            if self.lang_bilingual_list[i][2]:
                key = self.lang_bilingual_list[i][0]
                self.cache_dic[key] = {}
                self.cache_dic[key]['ori'] = self.lang_bilingual_list[i][1]
                self.cache_dic[key]['trans'] = self.lang_bilingual_list[i][2]
        if self.cache_dic:
            save_lang_file(self.cache_dic, self.cache_file_path)
        return self.cache_file_path


class FTBQuest:
    input_path = None
    quest_name = ''  # 任务文件名称，无文件类型后缀
    quest_type = 0  # 0-正常snbt,1-旧版本snbt,2-远古版本nbt
    raw_quest = ''  # 未解析的任务原文
    quest = None  # 解析后任务原文(snbt:dict,nbt:NBTFile)
    quest_local = {}  # 替换为使用键值后的任务
    # 任务标签，解析用
    end_tag = ['title', 'description', 'subtitle', 'text', 'hover', 'Lore', 'Name']
    stop_tag = ['{image:', '{@pagebreak}']

    def __init__(self, p: str):
        self.lang = Lang()  # 提取出的语言文件
        self.input_path = Path(p)
        self.quest_name = '' + list(self.input_path.parts)[-1].replace('.snbt', '')
        self.parse_quest_file(p)
        self.trans_lang()

    def parse_quest_file(self, p: str):
        file_name = list(self.input_path.parts)[-1]
        if file_name.endswith('.nbt'):
            self.quest_type = 2
            self.quest_name = file_name.replace('.nbt', '')
            nbt_file = nbt.NBTFile(p, 'rb')
            self.quest = nbt_file
        elif file_name.endswith('.snbt'):
            self.quest_type = 0
            self.quest_name = file_name.replace('.snbt', '')
            with open(p, 'r', encoding="utf-8") as fin:
                text = fin.read()
                # 检查是否为低版本
                self.raw_quest = text
                if re.search(r',\n(?!")', text):
                    self.quest_type = 1
                try:
                    quest = snbtlib.loads(text)
                    self.quest = quest
                except Exception as ex:
                    raise Exception('snbtlib调用出错，可能是python环境版本过低或其它问题！')
        else:
            raise Exception('不支持的任务类型！')

    def trans_lang(self):
        if self.quest_type == 2:
            pass
        else:
            prefix_list = ['ftbquests']
            if self.quest.get('chapter_groups'):
                prefix_list.append('chapter_groups')
            elif self.quest.get('loot_size'):
                prefix_list.append('reward_tables')
            elif self.quest.get('disable_gui'):
                prefix_list.append('data')
            else:
                prefix_list.append('chapter')
            prefix_list.append(self.quest_name)
            lang, self.quest_local = self.dfs(self.quest, prefix_list)
            self.lang.set_lang(lang, str(self.input_path))

    def save_quest_local(self, output_path: str) -> bool:
        try:
            quest_local_text = snbtlib.dumps(self.quest_local, compact=self.quest_type == 1)
            quest_local_text.replace('"B;"', 'B;')
            save_file(quest_local_text, output_path)
            return True
        except Exception as ex:
            return False

    def dfs(self, data, prefix: list, flag=False):
        # 递归遍历字典获取需要的文本
        res = OrderedDict()
        prefix_ = copy.deepcopy(prefix)
        if isinstance(data, dict):
            for k_, v_ in data.items():
                child, child_data = self.dfs(v_, prefix_ + [k_])
                data[k_] = child_data
                res.update(child)
        elif type(data) in [list, nbt.TAG_LIST]:
            length_ = len(data)
            for i in range(length_):
                child, child_data = self.dfs(data[i], prefix_ + [str(i + 1)] if length_ > 1 else prefix_, True)
                data[i] = child_data
                res.update(child)
        elif isinstance(data, str):
            if prefix_[-1] in self.end_tag or (flag and prefix_[-2] in self.end_tag):
                if bool(re.search(r'\S', data)):
                    if not any(tag in data for tag in self.stop_tag):
                        key = f"{'.'.join(prefix_)}"
                        res[key] = data
                        data = '{' + key + '}'
        elif isinstance(data, TAG) and data.id == nbt.TAG_STRING:
            if prefix_[-1] in self.end_tag or flag:
                if bool(re.search(r'\S', data.lang)):
                    if not any(tag in data.lang for tag in self.stop_tag):
                        key = f"{'.'.join(prefix_)}"
                        res[key] = data.lang
                        data.lang = '{' + key + '}'
        return res, data

    def back_fill(self, lang_: dict):
        text_ = snbtlib.dumps(self.quest_local)
        for key, value in lang_.items():
            text_ = text_.replace('{' + key + '}', str(value))
        return text_


class BetterQuest:
    input_path = None
    quest = {}
    quest_local = {}

    def __init__(self, p: str):
        self.lang = Lang()  # 提取出的语言文件
        self.input_path = p
        self.quest = parse_json_file(p)
        self.quest_local, lang_dic, _, _ = self.traverse_trans(self.quest)
        self.lang.set_lang(lang_dic, p)

    def traverse_trans(self, dictionary: dict, key_value=None, name_index=0, desc_index=0):
        if key_value is None:
            key_value = {}
        for key in dictionary.keys():
            if isinstance(dictionary[key], dict):
                dictionary_, key_value, name_index, desc_index = self.traverse_trans(dictionary[key], key_value,
                                                                                     name_index, desc_index)
                dictionary[key] = dictionary_
            else:
                if dictionary[key] == "":
                    continue
                elif key.find('name:') != -1:
                    key_content = 'bq.name.' + str(name_index)
                    name_index += 1
                elif key.find('desc:') != -1:
                    key_content = 'bq.desc.' + str(desc_index)
                    desc_index += 1
                else:
                    continue
                key_value[key_content] = dictionary[key]
                dictionary[key] = key_content

        return dictionary, key_value, name_index, desc_index

    def back_fill(self, lang_: dict):
        text_ = json.dumps(self.quest_local, indent=4, ensure_ascii=False)
        for key, value in lang_.items():
            text_ = text_.replace(key, str(value))
        return text_

    def dumps(self, dic: dict):
        text = json.dumps(dic, indent=1, ensure_ascii=False)
        return text


class Translator(QObject):
    api = cfg.get(cfg.translateApi)
    from_lang = ''
    to_lang = ''
    app_key = ''
    app_secret = ''
    access_token = None
    original = cfg.get(cfg.keepOriginal)
    spec_format = pyqtSignal(str)
    client = None
    model_name = cfg.get(cfg.modelName)
    local_client: LocalInferenceClient | None = None

    def __init__(self, from_lang: str, to_lang: str, key: str, secret: str):
        super().__init__()
        self.from_lang = from_lang
        self.to_lang = to_lang
        self.app_key = key
        self.app_secret = secret
        if self.api == '1':
            self.init_local_model()  # 检查本地推理服务可用性

    @staticmethod
    def bracket(m: re.Match):
        return "[&" + m.group(0) + "]"

    @staticmethod
    def debracket(m: re.Match):
        return m.group(0)[2:-1]

    def pre_process(self, line: str):
        if line.find('.jpg') + line.find('.png') != -2:
            self.spec_format.emit('注意:检测到图片格式，不翻译')
            return None
        if line.find(r'{\"') != -1:
            return None
        line = line.replace('\\\\&', 'PPP')
        if self.local_client is None:
            pattern = re.compile(r'&([a-z,0-9]|#[0-9,A-F]{6})')
            line = pattern.sub(self.bracket, line)
            self.spec_format.emit('注意:检测到彩色字符已预处理，不保证100%保留')
        line = re.sub(r'#\w+:\w+\b', MAGIC_WORD, re.sub(r'\\"', '\"', line))
        pattern = re.compile(r'(http|https)://(?:[-\w.]|(?:%[\da-fA-F]{2}))+')
        if re.search(pattern, line):
            self.spec_format.emit('注意:检测到包含网址，不翻译')
            return None
        return line

    def post_process(self, text_, translate):
        if self.local_client is None:
            pattern = re.compile(r'\[&&([a-z,0-9]|#[0-9,A-F]{6})]')
            translate = pattern.sub(self.debracket, translate)
            text_ = pattern.sub(self.debracket, text_)
        text_ = re.sub(r'(["\'])', r'\\\g<1>', text_)
        quotes = re.findall(r'#\w+:\w+\b', text_)
        if len(quotes) > 0:
            self.spec_format.emit('注意:检测到物品引用已处理，不保证100%安全')
            count = 0
            index = translate.find(MAGIC_WORD)
            while index != -1:
                translate = re.sub(MAGIC_WORD, quotes[count], translate, 1)
                count = count + 1
                index = translate.find(MAGIC_WORD)
        return translate + "[--" + text_ + "--]" if self.original else translate

    def get_access_token(self):
        url = "https://aip.baidubce.com/oauth/2.0/token"
        params = {
            "grant_type": "client_credentials",
            "client_id": self.app_key,
            "client_secret": self.app_secret
        }
        response = requests.get(url, params=params, timeout=3)
        result = response.json()
        access_token = result["access_token"]
        self.access_token = access_token

    def baidu_translate(self, text_: str):
        text_process = self.pre_process(text_)
        if text_process is None:
            return text_
        url_ = "https://aip.baidubce.com/rpc/2.0/mt/texttrans/v1"
        headers = {
            "Content-Type": "application/json;charset=utf-8"
        }
        body = {
            "from": self.from_lang,
            "to": self.to_lang,
            "q": text_process
        }
        if not self.access_token:
            self.get_access_token()
        params_ = {
            "access_token": self.access_token
        }
        response_ = requests.post(url_, headers=headers, params=params_, json=body, timeout=5)
        result_ = response_.json()
        try:
            translated_text = result_["result"]["trans_result"][0]["dst"]
        except Exception as e:
            translated_text = f"翻译出错：{str(e)}"
        return self.post_process(text_, translated_text)

    def init_local_model(self):
        """检查本地推理服务可达性；预处理逻辑仍在服务侧完成。"""
        from common.local_service import try_auto_start_service
        try_auto_start_service()
        self.local_client = LocalInferenceClient(cfg.get(cfg.localServiceUrl))
        ok, info = self.local_client.health()
        if not ok:
            self.spec_format.emit(
                f"本地推理服务不可达({cfg.get(cfg.localServiceUrl)}): {info}")
        elif info not in (None, "", "ok"):
            self.spec_format.emit(f"本地推理服务告警: {info}")

    def local_translate(self, text_: str):
        if self.local_client is None:
            self.init_local_model()
        text_process = self.pre_process(text_)
        if text_process is None:
            return text_
        try:
            output = self.local_client.translate(text_process, keep_original=False)
        except Exception as exc:  # noqa: BLE001
            return f"翻译出错: {type(exc).__name__}: {exc}"
        return self.post_process(text_, output)

    def init_openai_model(self):
        self.client = OpenAI(
            base_url=cfg.get(cfg.openaiUrl),
            organization=cfg.get(cfg.orgId),
            timeout=10,
            api_key=cfg.get(cfg.secretKey)
        )

    @staticmethod
    def generate_prompt(text: str) -> str:
        ref_data = [f'{item[1][0]}:{str(item[1][1])}' for item in global_aca.find(text.lower())]
        ref_prefix = '\n'.join(ref_data)
        prompt_dict = {
            "tasks": f"Translate the text below about minecraft into Chinese\n"
                     f"You can choose whether to refer to the following terms based on the context yourself:\n"
                     f"Do not return any other content besides the translated text\n",
            "terms": ref_prefix,
            "text": text
        }
        prompt = json.dumps(prompt_dict, indent=2, ensure_ascii=False)
        return prompt

    def gpt_translate(self, text_: str):
        params = dict(
            model=self.model_name,
            messages=[{"role": "user", "content": self.generate_prompt(text_)}],
            timeout=10
        )
        if not self.client:
            self.init_openai_model()
        completion = self.client.chat.completions.create(**params)
        return completion.choices[0].message.content

    @func_timer
    @func_set_timeout(20)
    def translate(self, text_: str):
        if self.api == '0':
            return self.baidu_translate(text_)
        elif self.api == '1':
            return self.local_translate(text_)
        elif self.api == '2':
            return self.gpt_translate(text_)
        else:
            return text_


class Mod:
    def __init__(self, path):
        self.path = path
        self.modName = ''
        self.langList = []
        self.get_info()

    def get_info(self):
        with zipfile.ZipFile(self.path, 'r') as jar:
            for file_info in jar.infolist():
                name = file_info.filename
                match1 = re.search(r"assets/([^/]+)", name)
                if match1:
                    self.modName = match1.group(1)
                match2 = re.search(r"lang/([^/]+)", name)
                if match2:
                    self.langList.append(match2.group(1))

    def get_lang_text(self, lang_name: str):
        with zipfile.ZipFile(self.path, 'r') as jar:
            for file_info in jar.infolist():
                name = file_info.filename
                if (r'lang/' + lang_name) in name:
                    with jar.open(name) as json_file:
                        content = json_file.read().decode('latin-1')
                        return content


class ResourcePack:
    def __init__(self, path: str):
        self.mods = []
        self.path = path
        self.get_mods_with_i18n()

    def get_mods_with_i18n(self):
        with zipfile.ZipFile(self.path, 'r') as file:
            for file_info in file.infolist():
                name = file_info.filename
                match1 = re.search(r"assets/([^/]+)", name)
                if match1:
                    if r'lang/zh_cn.' in name:
                        mod = match1.group(1)
                        if mod not in self.mods:
                            self.mods.append(mod)


class ACA:
    aca = ahocorasick.Automaton()

    def __init__(self):
        for k, v in TERMS.items():
            k = k.lower()  # 统一大小写
            if len(k) > 3:  # 排除长度小于3的词汇
                self.aca.add_word(k, (k, v))
        self.aca.make_automaton()

    def find(self, word: str) -> list:
        res = []
        word = word.lower()
        for item in self.aca.iter(word):
            res.append(item)
        if res:
            res.sort(key=lambda i: len(i[1][0]), reverse=True)  # 按匹配到术语的长度递减排序
        return res[:5]


global_aca = ACA()


class LangTranslateThread(QThread):
    finished = pyqtSignal()
    progress = pyqtSignal(int)
    index = pyqtSignal(str)
    info = pyqtSignal(str)
    error = pyqtSignal(str)
    remain_time = pyqtSignal(str)
    count = 0  # 总条数
    current_index = 0  # 当前指针

    def __init__(self, lang, from_lang: str, to_lang: str, app_key: str, app_secret: str):
        """
        翻译Lang中原文，并放回其中
        :param lang Lang或者list[Lang]
        :param from_lang 源语言
        :param to_lang 目标语言
        :param app_key 百度翻译API
        :param app_secret 百度翻译API
        """
        super().__init__()
        self.lang = lang
        self.translator = Translator(from_lang, to_lang, app_key, app_secret)
        self.calculate_count()

    def run(self):
        try:
            self.translator.spec_format.connect(self.handle_emit_process_info)
            if isinstance(self.lang, list):
                for lang in self.lang:
                    self.trans(lang)
            else:
                self.trans(self.lang)
        except func_timeout.exceptions.FunctionTimedOut:
            self.error.emit("  请求超时，请检查你的接口配置是否正确")
        except Exception as e:
            self.error.emit(str(e))
        else:
            self.finished.emit()

    def trans(self, lang):
        count = len(lang.lang_bilingual_list)
        str_count = 0
        for index in range(0, count):
            self.current_index += 1
            progress = (index + 1) / count * 100
            str_count += len(lang.lang_bilingual_list[index][1])
            self.progress.emit(progress)
            self.index.emit('翻译进度:%s,已耗字符：%s' % (str(index + 1), str(str_count)))
            self.info.emit('正在翻译:%s' % lang.lang_bilingual_list[index][1])
            trans, single_run_time = self.translator.translate(lang.lang_bilingual_list[index][1])
            self.remain_time.emit(self.estimated_time_remaining(single_run_time))
            lang.lang_bilingual_list[index][2] = trans
            lang.lang_bilingual_list[index][3] = trans
            self.info.emit('翻译结果为:%s' % trans)
        # 保存缓存文件
        lang.save_cache()

    def stop(self):
        self.terminate()
        self.wait()
        self.finished.emit()

    def handle_emit_process_info(self, info: str):
        self.info.emit(info)

    def estimated_time_remaining(self, single_run_time):
        remain_time = (self.count - self.current_index) * single_run_time
        seconds = remain_time % 60
        minutes = (remain_time - seconds) / 60
        return f"预计还需: %.f分%.f秒" % (minutes, seconds)

    def calculate_count(self):
        # 计算长度
        if isinstance(self.lang, list):
            for item in self.lang:
                self.count += len(item.lang_bilingual_list)
        else:
            self.count = len(self.lang.lang_bilingual_list)
        self.remain_time.emit(self.estimated_time_remaining(0.2))
