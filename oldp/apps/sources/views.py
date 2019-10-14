import datetime

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.shortcuts import render
from django.utils.translation import ugettext_lazy as _


@staff_member_required
@login_required
def stats_view(request):


    date_ranges = [
        {
            'name': 'last_day',
            'label': _('Last day'),
            'delta': {'days': 1},
        },
        {
            'name': 'last_week',
            'label': _('Last week'),
            'delta': {'weeks': 1},
        },
        {
            'name': 'last_month',
            'label': _('Last month'),
            'delta': {'weeks': 4},
        },
        {
            'name': 'last_3month',
            'label': _('Last three month'),
            'delta': {'weeks': 3*4},
        },
        {
            'name': 'total',
            'label': _('Total')
        }
    ]
    today = datetime.datetime.today()

    for idx, date_range in enumerate(date_ranges):
        if 'delta' in date_range:
            diff = today - datetime.timedelta(**date_range['delta'])
            diff_str = diff.strftime('%Y-%m-%d')

            where_clause = ' WHERE c.created_date > "{}"'.format(diff_str)
        else:
            where_clause = ''

        query = '''
    
         SELECT s.name as source_name,
        COUNT(*) as total,
        SUM(c.private) as not_published,
        SUM(c.court_id > 1) as with_court,
        SUM(c.court_id <= 1) as without_court,
        DATE_FORMAT(MAX(c.created_date), "%Y-%m-%d %H:%i") as last_created_date
        
         FROM cases_case c
         JOIN sources_source s ON c.source_id = s.id
         ''' + where_clause + '''
         GROUP BY source_id
         ORDER BY source_name'''

        with connection.cursor() as cursor:
            cursor.execute(query)

            columns = [col[0] for col in cursor.description]
            date_ranges[idx]['data'] = [
                dict(zip(columns, row))
                for row in cursor.fetchall()
            ]

    return render(request, 'sources/stats.html', {
        'title': _('Statistics'),
        'date_ranges': date_ranges,
        'columns': [
            'source_name',
            'total',
            'not_published',
            'with_court',
            'without_court',
            'last_created_date',
        ]
    })
