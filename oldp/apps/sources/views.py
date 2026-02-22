import datetime

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _


@staff_member_required
@login_required
def stats_view(request):
    date_ranges = [
        {
            "name": "last_day",
            "label": _("Last day"),
            "delta": {"days": 1},
        },
        {
            "name": "last_week",
            "label": _("Last week"),
            "delta": {"weeks": 1},
        },
        {
            "name": "last_month",
            "label": _("Last month"),
            "delta": {"weeks": 4},
        },
        {
            "name": "last_3month",
            "label": _("Last three month"),
            "delta": {"weeks": 3 * 4},
        },
        {"name": "total", "label": _("Total")},
    ]
    today = datetime.datetime.today()

    for idx, date_range in enumerate(date_ranges):
        if "delta" in date_range:
            diff = today - datetime.timedelta(**date_range["delta"])
            where_clause = " WHERE c.created_date > %s"
            params = [diff.strftime("%Y-%m-%d")]
        else:
            where_clause = ""
            params = []

        query = """
         SELECT s.name as source_name,
        COUNT(*) as total,
        SUM(c.review_status != 'accepted') as not_published,
        SUM(c.court_id > 1) as with_court,
        SUM(c.court_id <= 1) as without_court,
        MAX(c.created_date) as last_created_date

         FROM cases_case c
         JOIN sources_source s ON c.source_id = s.id
         """
        query += where_clause
        query += """
         GROUP BY source_id
         ORDER BY source_name"""

        with connection.cursor() as cursor:
            cursor.execute(query, params)

            columns = [col[0] for col in cursor.description]
            rows = []
            for row in cursor.fetchall():
                row_dict = dict(zip(columns, row))
                if row_dict.get("last_created_date") and hasattr(
                    row_dict["last_created_date"], "strftime"
                ):
                    row_dict["last_created_date"] = row_dict[
                        "last_created_date"
                    ].strftime("%Y-%m-%d %H:%M")
                rows.append(row_dict)
            date_ranges[idx]["data"] = rows

    return render(
        request,
        "sources/stats.html",
        {
            "title": _("Statistics"),
            "date_ranges": date_ranges,
            "columns": [
                "source_name",
                "total",
                "not_published",
                "with_court",
                "without_court",
                "last_created_date",
            ],
        },
    )
