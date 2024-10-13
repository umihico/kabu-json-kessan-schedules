import re
import requests
from lxml import html
import datetime
from dateutil.relativedelta import relativedelta
import json

# import requests_cache
# session = requests_cache.CachedSession('cache', expire_after=9999999)
session = requests.Session()

raw_data = []
for i in range(1, 13):
    month = f"{i:02d}"
    for page_index in range(1, 100):
        try:
            url = f"""https://www.nikkei.com/markets/kigyo/money-schedule/kessan/?ResultFlag=4&KessanMonth={
                month}&hm={page_index}"""
            print(f"month: {month}, page_index: {page_index}")
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            body = response.content.decode("utf-8")

            # "2351～2348件目を表示(全2348件)"
            REGEX_PATTERN = r"(\d+)～(\d+)件目を表示\(全(\d+)件\)"
            match = re.search(REGEX_PATTERN, body)
            first_page_only = match is None  # 1ページしかない場合は、このパターンは見つからない
            if first_page_only and page_index != 1:
                raise Exception(
                    f"Regex pattern not found, but page_index is not 1: {url}")
            tree = html.fromstring(body)
            headers = [th.text_content() for th in tree.xpath(
                "//table[@summary='決算発表スケジュール表']/thead/tr/th")]
            if headers != ["決算発表日", "証券コード", "会社名", "関連情報", "決算期", "決算種別", "業種", "上場市場"]:
                raise Exception(
                    f"Table header is not as expected: {headers}")
            rows = tree.xpath(
                "//table[@summary='決算発表スケジュール表']/tbody/tr")
            if len(rows) == 0:
                raise Exception(f"rows not found: {url}")
            for (index, row) in enumerate(rows):
                cols = [td.text_content() for td in row.xpath(".//td | .//th")]
                if len(cols) != 8:
                    raise Exception(
                        f"Table row does not have 8 columns: {cols}, index: {index}")
                json_data = {
                    "決算発表日": cols[0],
                    "証券コード": cols[1],
                    "会社名": cols[2],
                    # "関連情報": cols[3], # 常に'適時開示'の文字列しかないので、無視
                    "決算期": cols[4],
                    "決算種別": cols[5].replace("\xa0", ""),
                    "業種": cols[6],
                    "上場市場": cols[7],
                }
                raw_data.append(json_data)
                # print(json_data)
            if first_page_only:
                break
            else:
                first, second, total = match.groups()
                if int(second) >= int(total):  # 一致するはずだが、一応超えたパターンも考慮
                    break
        except Exception as e:
            print(body)
            print(url)
            raise e


kessan_month_patterns = {
    '1': [4, 7, 10, 1],
    '2': [5, 8, 11, 2],
    '3': [6, 9, 12, 3],
    '4': [7, 10, 1, 4],
    '5': [8, 11, 2, 5],
    '6': [9, 12, 3, 6],
    '7': [10, 1, 4, 7],
    '8': [11, 2, 5, 8],
    '9': [12, 3, 6, 9],
    '10': [1, 4, 7, 10],
    '11': [2, 5, 8, 11],
    '12': [3, 6, 9, 12]
}

final_data = []
for i, data in enumerate(raw_data):
    try:
        date_str = data["決算発表日"]
        if date_str in ["--", "---"]:
            final_data.append({
                **data,
                "決算月配列": None,
                "決算月": None,
                "決算発表月配列": None,
                "発表日数差": None,
                "決算日": None,
            })
            continue
        if "上旬" in date_str:
            date_str = date_str.replace("上旬", "01")
        elif "中旬" in date_str:
            date_str = date_str.replace("中旬", "15")
        elif "下旬" in date_str:
            date_str = date_str.replace("下旬", "28")
        pattern = kessan_month_patterns[data["決算期"].replace("月期", "")]
        month = {
            "第１": 0,
            "第２": 1,
            "第３": 2,
            "第４": 3,
            "本": 3,
        }[data["決算種別"]]

        release_date = datetime.datetime.strptime(date_str, "%Y/%m/%d")
        kessan_date = [d for d in
                       [
                           datetime.datetime(release_date.year,
                                             pattern[month], 1),
                           datetime.datetime(release_date.year - 1, pattern[month], 1)]
                       if d < release_date
                       ][0] + relativedelta(months=1) - datetime.timedelta(days=1)
        delta = release_date - kessan_date
        final_data.append({
            **data,
            "決算月配列": pattern,
            "決算月": month,
            "発表日数差": delta.days,
            "決算発表月配列": kessan_month_patterns[str(release_date.month)],
            "決算日": kessan_date.strftime("%Y/%m/%d"),
        })
    except Exception as e:
        print("index: ", i)
        print("data:", data)
        raise e


def sort_func(x):
    # "2024/10/2", "2024/10/20", "---", "2024/10/上旬"等
    date_str = x["決算発表日"]
    if "上旬" in date_str:
        date_str = date_str.replace("上旬", "01")
    elif "中旬" in date_str:
        date_str = date_str.replace("中旬", "15")
    elif "下旬" in date_str:
        date_str = date_str.replace("下旬", "28")
    today = datetime.datetime.now()
    try:
        parsed = datetime.datetime.strptime(date_str, "%Y/%m/%d") if date_str not in ["--", "---"] else datetime.datetime.strptime(
            "9999/12/31", "%Y/%m/%d")
    except ValueError:
        print(x)
        raise Exception(f"Unexpected date string: {date_str}")
    if parsed < today:
        parsed = datetime.datetime.strptime("9999/12/31", "%Y/%m/%d")
    return parsed


final_data = sorted(final_data, key=sort_func)

if len(final_data) < 4000:
    raise Exception("件数が少なすぎる")

with open("schedules.json", "w", encoding="utf-8") as json_file:
    json_file.write(json.dumps(final_data, ensure_ascii=False, indent=4))
