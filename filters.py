# filters.py
def build_filters(date_from, date_to, in_process, processed, company_id):
    f = {}
    if date_from:
        f["date_from"] = date_from
    if date_to:
        f["date_to"] = date_to
    if in_process is not None:
        f["in_process"] = in_process
    if processed is not None:
        f["processed"] = processed
    if company_id:
        f["company_id"] = company_id
    return f