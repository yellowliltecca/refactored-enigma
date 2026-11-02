#!/usr/bin/env python3
"""Safely refresh the SGU 111 group timetable. Requires requests and beautifulsoup4.

Do not replace a good snapshot on an invalid response or unexpected page layout.
"""
from __future__ import annotations
import datetime as dt
import json
import re
import pathlib
import sys
import unicodedata
import requests
from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGET = ROOT / 'data' / 'schedule.json'
SOURCE = 'https://www.sgu.ru/schedule/knt/do/111'
CALENDAR = 'https://www.sgu.ru/schedule/knt'
HEADERS = {'User-Agent': 'SGU111Schedule/1.0 (+personal student timetable; contact via GitHub)', 'Accept-Language': 'ru-RU,ru;q=0.9'}
SLOTS = [('08:20','09:50'),('10:00','11:35'),('12:05','13:40'),('13:50','15:25'),('15:35','17:10'),('17:20','18:40'),('18:45','20:05'),('20:10','21:30')]
MONTHS = {'января':1,'февраля':2,'марта':3,'апреля':4,'мая':5,'июня':6,'июля':7,'августа':8,'сентября':9,'октября':10,'ноября':11,'декабря':12}
CLASS_RE = re.compile(r'(?<!\w)(ЛЕКЦИЯ|ПРАКТИКА|ЛАБОРАТОРНАЯ РАБОТА|ЛАБОРАТОРНАЯ)(?!\w)', re.I)
TEACHER_RE = re.compile(r'(?<!\w)[А-ЯЁ][а-яё-]+\s+[А-ЯЁ]\.\s*(?:[А-ЯЁ]\.)?', re.U)


def norm(text: str) -> str:
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', text or '').replace('\u00a0',' ')).strip()


def get(url):
    response = requests.get(url, headers=HEADERS, timeout=35)
    response.raise_for_status()
    response.encoding = response.apparent_encoding if response.encoding is None or response.encoding.lower() == 'iso-8859-1' else response.encoding
    if len(response.content) < 1800:
        raise ValueError(f'Unexpected tiny page at {url}')
    return BeautifulSoup(response.text, 'html.parser')


def find_lesson_table(soup):
    best = None
    score_max = 0
    for table in soup.find_all('table'):
        rows=table.find_all('tr')
        days=norm(table.get_text(' ',strip=True)).lower()
        score=0
        if 'понедельник' in days and 'пятница' in days: score+=20
        for tr in rows:
            cells=tr.find_all(['td','th'],recursive=False)
            if len(cells)>=6 and re.search(r'\b\d{1,2}:\d{2}\b',norm(cells[0].get_text(' ',strip=True))): score+=3
        if score>score_max:
            score_max=score;best=table
    if not best or score_max<24:
        raise ValueError('Did not find the main university lesson table')
    return best


def parse_lesson(text,day,start,end):
    text=norm(text)
    m=CLASS_RE.match(text)
    if not m:
        return None
    kind={'лекция':'lecture','практика':'practice','лабораторная':'lab','лабораторная работа':'lab'}.get(m.group(1).lower(),'other')
    rest=text[m.end():].strip()
    # Explicit university marker: Ч = числитель; З = знаменатель.
    week='both'
    mw=re.match(r'^(Ч|З)(?=\s|$)',rest,re.I)
    if mw:
        week='numerator' if mw.group(1).upper()=='Ч' else 'denominator'
        rest=rest[mw.end():].strip()
    groups=[]
    mg=re.match(r'^(\d(?:\s*(?:и|,)\s*\d)*)\s*под(?:г(?:руппа)?)?\.?(?=\s|$)',rest,re.I)
    if mg:
        groups=[int(n) for n in re.findall(r'\d',mg.group(1))]
        rest=rest[mg.end():].strip()
    changed=bool(re.search(r'↺|после смены расписания',rest,re.I))
    rest=re.sub(r'↺','',rest).strip()
    # Instructor names usually separate subject from place.
    matches=list(TEACHER_RE.finditer(rest))
    tm=matches[-1] if matches else None
    teacher=norm(tm.group(0)) if tm else ''
    if tm:
        title=norm(rest[:tm.start()])
        location=norm(rest[tm.end():])
    else:
        ml=re.search(r'\b\d{1,2}\s*корпус\b|\bДистанционно\b|\bСпортивный комплекс\b',rest,re.I)
        title=norm(rest[:ml.start()]) if ml else rest
        location=norm(rest[ml.start():]) if ml else ''
    # Sometimes a location appears *before* the subject on the university site.
    preloc=re.match(r'^((?:\d+\s+корпус[,\s]+[^,]*?(?:ауд\.|комната|каб\.)|Дистанционно)\s+)(.*)$',title,re.I)
    if preloc:
        location=norm(preloc.group(1)+' '+location)
        title=norm(preloc.group(2))
    notes=''
    if re.match(r'^Бассейн\b',title,re.I):
        title=re.sub(r'^Бассейн\s+', '', title, flags=re.I)
        notes='Бассейн (пометка СГУ)'
    if title: title=title[0].upper()+title[1:]
    if not title: raise ValueError(f'Empty subject in {text!r}')
    return {'day':day,'start':start,'end':end,'kind':kind,'title':title,'teacher':teacher,'location':location,'week':week,'groups':groups,'note':notes,'after_change':changed}


def parse_lessons(soup):
    table=find_lesson_table(soup)
    lessons=[]
    seen_slots=set()
    for tr in table.find_all('tr'):
        cells=tr.find_all(['td','th'],recursive=False)
        if len(cells)<7: continue
        celltext=norm(cells[0].get_text(' ',strip=True))
        times=re.findall(r'(?<!\d)\d{1,2}:\d{2}(?!\d)',celltext)
        if len(times)<2: continue
        start,end=times[0],times[1]
        if (start,end) not in SLOTS: continue
        seen_slots.add((start,end))
        for day,td in enumerate(cells[1:7]):
            # Divide at each class type, not at individual nested DOM children.
            raw=norm(td.get_text(' ',strip=True))
            if not raw:continue
            blocks=list(CLASS_RE.finditer(raw))
            for i,mark in enumerate(blocks):
                segment=raw[mark.start():blocks[i+1].start() if i+1<len(blocks) else len(raw)]
                entry=parse_lesson(segment,day,start,end)
                if entry:lessons.append(entry)
    if len(seen_slots)<4 or len(lessons)<5 or not any(l['title'].lower().startswith('математический') or 'программирован' in l['title'].lower() for l in lessons):
        raise ValueError(f'Suspect schedule: {len(lessons)} lessons, {len(seen_slots)} time slots')
    # Keep duplicate teacher entries when representing separate subgroups.
    return sorted(lessons,key=lambda x:(x['day'],x['start'],x['week'],str(x['groups']),x['title']))


def parse_exams(soup):
    for table in soup.find_all('table'):
        header=norm(table.get_text(' ',strip=True)).lower()
        if 'отчётность' not in header and 'отчетность' not in header: continue
        if 'преподаватель' not in header: continue
        out=[]
        for tr in table.find_all('tr'):
            cells=tr.find_all(['td','th'],recursive=False)
            if len(cells)<4:continue
            row=[norm(c.get_text(' ',strip=True)) for c in cells[:4]]
            m=re.match(r'(\d{1,2})\s+([а-яё]+)\s+(\d{4})\s*г?\.?\s*(\d{1,2}:\d{2})?',row[0],re.I)
            if not m:continue
            month=MONTHS.get(m.group(2).lower())
            if not month:continue
            day=int(m.group(1));year=int(m.group(3))
            typ=re.match(r'^(Дифференцированный зачет|Дифференцированный зачёт|Экзамен|Зачет|Зачёт|Консультация)\s+',row[1],re.I)
            kind=typ.group(1) if typ else 'Аттестация'
            title=row[1][typ.end():] if typ else row[1]
            out.append({'date':dt.date(year,month,day).isoformat(),'time':m.group(4) or '', 'kind':kind,'title':title,'teacher':row[2],'location':row[3]})
        return out
    return []


def parse_calendar(soup):
    text=norm(soup.get_text(' ',strip=True)).lower()
    # The source publishes explicit week labels, so do not use generic ISO week parity.
    chunks=list(re.finditer(r'([12])\s*семестр\s+(\d{4})\s*г',text))
    pattern=re.compile(r'(?<!\d)(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s*[–—-]\s*(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(числитель|знаменатель)',re.I)
    found=[]
    for match in pattern.finditer(text):
        prior=[h for h in chunks if h.start()<match.start()]
        if not prior:continue
        year=int(prior[-1].group(2))
        month=MONTHS[match.group(2)]
        day=int(match.group(1))
        try: date=dt.date(year,month,day)
        except ValueError:continue
        monday=date-dt.timedelta(days=date.weekday())
        found.append({'start':monday.isoformat(),'type':'numerator' if match.group(5)=='числитель' else 'denominator'})
    # Do not erase a known calendar because the university changes its HTML.
    return list({x['start']:x for x in found}.values()) if len(found)>=5 else None


def key(entry):
    # When a teacher, room or subject changes at the same time, classify as edit.
    return (entry['day'],entry['start'],entry['week'],tuple(entry['groups']))


def changes(old,new):
    old_map={}
    for e in old:old_map.setdefault(key(e),[]).append(e)
    new_map={}
    for e in new:new_map.setdefault(key(e),[]).append(e)
    out=[]
    for k in sorted(set(old_map)|set(new_map)):
        before=old_map.get(k,[])
        after=new_map.get(k,[])
        if before==after:continue
        for e in after:
            if e not in before:
                out.append({'event':'changed' if before else 'added','day':e['day'],'time':e['start'],'text':e['title'],'detail':(e['location'] or e['teacher'])})
        if before and not after:
            for e in before:out.append({'event':'removed','day':e['day'],'time':e['start'],'text':e['title'],'detail':''})
    return out[:18]


def main():
    old=json.loads(TARGET.read_text(encoding='utf-8'))
    soup=get(SOURCE)
    full=norm(soup.get_text(' ',strip=True))
    if '111 группа' not in full or 'Факультет компьютерных наук' not in full:
        raise ValueError('University page does not belong to SGU KNiIT group 111')
    date_match=re.search(r'Дата последнего обновления\s*:\s*(\d{2}\.\d{2}\.\d{4})',full)
    if not date_match:raise ValueError('University update date missing')
    lessons=parse_lessons(soup)
    exams=parse_exams(soup)
    try:
        calendar=parse_calendar(get(CALENDAR))
    except Exception as ex:
        print(f'Calendar refresh warning: {ex}',file=sys.stderr)
        calendar=None
    current=old.copy()
    current.update({'source_updated':date_match.group(1),'fetched_at':dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),'initial_snapshot':False,'lessons':lessons,'exams':exams,'week_calendar':calendar or old['week_calendar']})
    if old.get('initial_snapshot'):
        current['changes']=[]
        current['changes_at']=None
    elif old['lessons']!=lessons or old.get('exams')!=exams:
        current['changes']=changes(old['lessons'],lessons)
        current['changes_at']=current['fetched_at']
    else:
        current['changes']=old.get('changes',[])
        current['changes_at']=old.get('changes_at')
    # Avoid a commit just because we checked again; record fetching time only when new source content.
    if current['lessons']==old['lessons'] and current['exams']==old.get('exams',[]) and current['source_updated']==old['source_updated'] and current['week_calendar']==old['week_calendar']:
        if old.get('initial_snapshot'):
            current['fetched_at']=dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
        else:
            print('No university changes; keeping current published snapshot.')
            return
    TARGET.write_text(json.dumps(current,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Updated {len(lessons)} lessons, {len(exams)} exams; SGU date {current["source_updated"]}')

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(f'Update FAILED; previous verified data preserved: {exc}',file=sys.stderr)
        sys.exit(1)
