# Retrieve fic ids from an AO3 search
# Will return in searched order
# Saves ids to a csv for later use e.g. to retrieve fic text

# Options:
# Only retrieve multichapter fics
# Modify search to include a list of tags
#      (e.g. you want all fics tagged either "romance" or "fluff")

from bs4 import BeautifulSoup, ResultSet
import re
import time
import requests
import csv
import sys
import datetime
import argparse
import os

page_empty = False
base_url = ""
url = ""
num_requested_fic = 0
num_recorded_fic = 0
csv_name = ""
multichap_only = ""
tags = []
start_time = None

# keep track of all processed ids to avoid repeats:
# this is separate from the temporary batch of ids
# that are written to the csv and then forgotten
seen_ids = set()

# 
# Ask the user for:
# a url of a works listed page
# e.g. 
# https://archiveofourown.org/works?utf8=%E2%9C%93&work_search%5Bsort_column%5D=word_count&work_search%5Bother_tag_names%5D=&work_search%5Bquery%5D=&work_search%5Blanguage_id%5D=&work_search%5Bcomplete%5D=0&commit=Sort+and+Filter&tag_id=Harry+Potter+-+J*d*+K*d*+Rowling
# https://archiveofourown.org/tags/Harry%20Potter%20-%20J*d*%20K*d*%20Rowling/works?commit=Sort+and+Filter&page=2&utf8=%E2%9C%93&work_search%5Bcomplete%5D=0&work_search%5Blanguage_id%5D=&work_search%5Bother_tag_names%5D=&work_search%5Bquery%5D=&work_search%5Bsort_column%5D=word_count
# how many fics they want
# what to call the output csv
# 
# If you would like to add additional search terms (that is should contain at least one of, but not necessarily all of)
# specify these in the tag csv, one per row. 

def get_args():
    global base_url
    global url
    global csv_name
    global num_requested_fic
    global multichap_only
    global tags

    parser = argparse.ArgumentParser(description='Scrape AO3 work IDs given a search URL')
    parser.add_argument(
        'url', metavar='URL',
        help='a single URL pointing to an AO3 search page')
    parser.add_argument(
        '--out_csv', default='work_ids',
        help='csv output file name')
    parser.add_argument(
        '--header', default='',
        help='user http header')
    parser.add_argument(
        '--num_to_retrieve', default='a', 
        help='how many fic ids you want')
    parser.add_argument(
        '--multichapter_only', default='', 
        help='only retrieve ids for multichapter fics')
    parser.add_argument(
        '--tag_csv', default='',
        help='provide an optional list of tags; the retrieved fics must have one or more such tags')
    parser.add_argument(
        "--start_page", default=1,
        help="start page number (default 1)"
    )

    args = parser.parse_args()
    url = args.url
    csv_name = str(args.out_csv)
    
    # defaults to all
    if (str(args.num_to_retrieve) == 'a'):
        num_requested_fic = -1
    else:
        num_requested_fic = int(args.num_to_retrieve)

    multichap_only = str(args.multichapter_only)
    if multichap_only != "":
        multichap_only = True
    else:
        multichap_only = False

    tag_csv = str(args.tag_csv)
    if (tag_csv):
        with open(tag_csv, "r") as tags_f:
            tags_reader = csv.reader(tags_f)
            for row in tags_reader:
                tags.append(row[0])

    return args

# 
# navigate to a works listed page,
# then extract all work ids
# 
def get_stats(header_info='') -> list[tuple]:
    """
    Get the stats for each work on the page

    :return: list of tuples, each containing the stats for a work
    in the form (id, chapters, words, kudos, title)
    """
    global page_empty
    global seen_ids

    # make the request. if we 429, try again later
    print("Requesting page: ", url)
    headers = {'user-agent' : header_info}
    req = requests.get(url, headers=headers)
    while req.status_code == 429:
        # >5 second delay between requests as per AO3's terms of service
        print("Request answered with Status-Code 429, retrying...")
        time.sleep(10)
        req = requests.get(url, headers=headers)

    soup = BeautifulSoup(req.text, "lxml")

    # some responsiveness in the "UI"
    # sys.stdout.write('.')
    # sys.stdout.flush()
    # Each of the works is the whole story 'box'
    works = soup.select("li.work.blurb.group")
    # see if we've gone too far and run out of fic: 
    if (len(works) == 0):
        print("No more works found.")
        page_empty = True

    # process list for new fic ids
    # Turns out counting chapter numbers is not very accurate.
    # So we're going to filter based on word count, since that's what we're 
    # sorting by anyway.
    ids = []
    stats = []
    for work in works:
        id = work.get('id')
        id = id[5:]

        if not id in seen_ids:
            ids.append(id)
            seen_ids.add(id)
            chaps, words, kudos, title = get_work_stats(work)
            
            if (words == -1):
                print(f"Hit a fic with no word count")
            elif (words <= 5000):
                print(f"Hit a fic with less than 5000 words, stopping search.")
                break

            stats.append((id, chaps, words, kudos, title))

    return stats

def get_work_stats(work: ResultSet) -> tuple:
    chaps_sel = work.find('dd', class_="chapters")
    words_sel = work.find('dd', class_="words")
    kudos_sel = work.find('dd', class_="kudos")
    title_sel = work.find('h4', class_="heading").find('a')
    
    try:
        title = title_sel.text.strip()
    except:
        print("Error: could not find title.")
        title = "No title found"

    try:
        chapters = int(chaps_sel.text.split('/')[0].replace(',', ''))
    except:
        print("Error: could not find chapter count.")
        chapters = -1
    try:
        words = int(words_sel.text.replace(',', ''))
    except:
        print("Error: could not find word count.")
        words = -1
    try:
        kudos = int(kudos_sel.text.replace(',', ''))
    except:
        print("Error: could not find kudos count.")
        kudos = -1
        
    return chapters, words, kudos, title

def update_url_to_page(page: int):
    global url
    key = "page="
    start = url.find(key)
    if (start != -1):
        page_start_index = start + len(key)
        page_end_index = url.find("&", page_start_index)
        if (page_end_index != -1):
            url = url[:page_start_index] + str(page) + url[page_end_index:]
        else:
            url = url[:page_start_index] + str(page)
    else:
        if (url.find("?") != -1):
            url = url + "&page=" + str(page)
        else:
            url = url + "?page=" + str(page)

# 
# update the url to move to the next page
# note that if you go too far, ao3 won't error, 
# but there will be no works listed
# 
def update_url_to_next_page():
    global url
    key = "page="
    start = url.find(key)
    page = -1

    # there is already a page indicator in the url
    if (start != -1):
        # find where in the url the page indicator starts and ends
        page_start_index = start + len(key)
        page_end_index = url.find("&", page_start_index)
        # if it's in the middle of the url
        if (page_end_index != -1):
            page = int(url[page_start_index:page_end_index]) + 1
            url = url[:page_start_index] + str(page) + url[page_end_index:]
        # if it's at the end of the url
        else:
            page = int(url[page_start_index:]) + 1
            url = url[:page_start_index] + str(page)

    # there is no page indicator, so we are on page 1
    else:
        # there are other modifiers
        if (url.find("?") != -1):
            url = url + "&page=2"
        # there an no modifiers yet
        else:
            url = url + "?page=2"

    return page


# modify the base_url to include the new tag, and save to global url
def add_tag_to_url(tag):
    global url
    key = "&work_search%5Bother_tag_names%5D="
    if (base_url.find(key)):
        start = base_url.find(key) + len(key)
        new_url = base_url[:start] + tag + "%2C" + base_url[start:]
        url = new_url
    else:
        url = base_url + "&work_search%5Bother_tag_names%5D=" + tag


# 
# after every page, write the gathered ids
# to the csv, so a crash doesn't lose everything.
# include the url where it was found,
# so an interrupted search can be restarted
# 
def write_stats_to_csv(all_stats: list[tuple]):
    global num_recorded_fic
    with open(csv_name + ".csv", 'a', newline="", encoding="utf-8") as csvfile:
        wr = csv.writer(csvfile, delimiter=',')
        # if (len(all_stats) > 0):
            # wr.writerow(["id", "chapters", "words", "kudos", "title"])

        for stats in all_stats:
            # wr.writerow(stats + (url,))
            wr.writerow(stats)
            num_recorded_fic = num_recorded_fic + 1
            print(f"Title: {stats[-1]}, Chapters: {stats[1]}, Words: {stats[2]}, Kudos: {stats[3]}")

# 
# if you want everything, you're not done
# otherwise compare recorded against requested.
# recorded doesn't update until it's actually written to the csv.
# If you've gone too far and there are no more fic, end. 
# 
def not_finished():
    if (page_empty):
        return False

    if (num_requested_fic == -1):
        return True
    else:
        if (num_recorded_fic < num_requested_fic):
            return True
        else:
            return False

# 
# include a text file with the starting url,
# and the number of requested fics
# 
def make_readme():
    with open(csv_name + "_readme.txt", "w") as text_file:
        text_file.write("url: " + url + "\n" + "num_requested_fic: " + str(num_requested_fic) + "\n" + "retreived on: " + str(datetime.datetime.now()))

# reset flags to run again
# note: do not reset seen_ids
def reset():
    global page_empty
    global num_recorded_fic
    page_empty = False
    num_recorded_fic = 0

def process_for_ids(header_info=''):
    while(not_finished()):
        stats = get_stats(header_info)
        write_stats_to_csv(stats) # Remove the URL
        new_page = update_url_to_next_page()

        print(f"Page {new_page} processed.")
        print("Runtime: ", fmt_sec(int(time.time() - start_time)))
        # 5 second delay between requests as per AO3's terms of service
        time.sleep(5)

def fmt_sec(sec: int) -> str:
    """ Format seconds into a string: HH:MM:SS """
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def load_existing_ids():
    global seen_ids

    if (os.path.exists(csv_name + ".csv")):
        print("skipping existing IDs...\n")
        with open(csv_name + ".csv", 'r') as csvfile:
            id_reader = csv.reader(csvfile)
            for row in id_reader:
                seen_ids.add(row[0])
    else:
        print("no existing file; creating new file...\n")

def main():
    global start_time
    args = get_args()
    header_info = str(args.header)
    # make_readme()

    # print ("loading existing file ...\n")
    # load_existing_ids()

    print("processing...\n")

    update_url_to_page(int(args.start_page))

    start_time = time.time()
    process_for_ids(header_info)

    print("That's all, folks.")

main()
