import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import update
from bs4 import BeautifulSoup

def fixture():
    rows=['<tr><th>Время</th>'+''.join(f'<th>{d}</th>' for d in ['Понедельник','Вторник','Среда','Четверг','Пятница','Суббота'])+'</tr>']
    for st,en in update.SLOTS:
        cells=['']*6
        if st=='08:20':
            cells[0]='<div>ПРАКТИКА Иностранный язык Алексеева Д. А. 12 корпус, 125 комната</div>'
            cells[1]='<div>ПРАКТИКА З информационные технологии и программирование Ковешников Д. В. 12 корпус, 418 комната</div>'
            cells[3]='<div>ЛЕКЦИЯ Алгебра и геометрия Бредихин Д. А. 12 корпус, 420/421 комната</div>'
        if st=='13:50':
            cells[0]='<div>ПРАКТИКА 1 под информационные технологии и программирование Павлова А. А. 12 корпус, 329 комната</div>'
            cells[1]='<div>ЛЕКЦИЯ Ч Основы Российской государственности Дорошин И. А. 12 корпус, 333 комната</div><div>ЛЕКЦИЯ З Теоретическая информатика Иванов А. С. 12 корпус, 310 комната</div>'
        if st=='10:00':cells[2]='<div>ПРАКТИКА Математический анализ Комиссарова Н. Е. 12 корпус, 420/421 комната</div>'
        rows.append(f'<tr><td>{st}<br>{en}</td>'+''.join(f'<td>{x}</td>' for x in cells)+'</tr>')
    return BeautifulSoup('<html><body><table>'+''.join(rows)+'</table></body></html>','html.parser')

def test_parse():
    a=update.parse_lessons(fixture())
    assert len(a)==7,len(a)
    denominator=[i for i in a if i['day']==1 and i['week']=='denominator']
    assert len(denominator)==2
    assert denominator[0]['title']=='Информационные технологии и программирование' or denominator[0]['title']=='Теоретическая информатика'
    assert any(i['groups']==[1] for i in a)
    assert any(i['location']=='12 корпус, 420/421 комната' for i in a)
    assert all(i['teacher'] for i in a)

def test_parity():
    html='<div>1 семестр 2026 г. 01 СЕНТЯБРЯ – 06 СЕНТЯБРЯ ЧИСЛИТЕЛЬ 07 СЕНТЯБРЯ – 13 СЕНТЯБРЯ ЗНАМЕНАТЕЛЬ 14 СЕНТЯБРЯ – 20 СЕНТЯБРЯ ЧИСЛИТЕЛЬ 21 СЕНТЯБРЯ – 27 СЕНТЯБРЯ ЗНАМЕНАТЕЛЬ 28 СЕНТЯБРЯ – 04 ОКТЯБРЯ ЧИСЛИТЕЛЬ 02 НОЯБРЯ – 08 НОЯБРЯ ЗНАМЕНАТЕЛЬ</div>'
    res=update.parse_calendar(BeautifulSoup(html,'html.parser'))
    assert res[-1]=={'start':'2026-11-02','type':'denominator'}

if __name__=='__main__':test_parse();test_parity();print('All parser fixture tests passed')
