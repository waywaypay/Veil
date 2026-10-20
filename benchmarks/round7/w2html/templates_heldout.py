"""Held-out W-2 print layouts (16 templates).

Each function takes a form dict and returns a complete HTML string.
No JavaScript, no external resources; inline CSS only; US Letter via @page.
"""
from html import escape as _esc


# ---------------------------------------------------------------- helpers
def _g(f, k, d=""):
    v = f.get(k)
    return d if v is None else str(v)


def e(f, k, d=""):
    return _esc(_g(f, k, d))


def yr(f):
    return _esc(_g(f, "year") or "2025")


def addr_lines(f):
    return ["<span class='nw'>%s</span>" % _esc(x) for x in _g(f, "address").split("\n") if x.strip()]


def emp_lines(f):
    return ["<span class='nw'>%s</span>" % _esc(x) for x in _g(f, "employer").split("\n") if x.strip()]


def box12(f):
    out = []
    for s in "abcd":
        c, a = _g(f, "c12" + s), _g(f, "a12" + s)
        if c or a:
            out.append((s, _esc(c), _esc(a)))
    return out


def money(v):
    return "$" + v if v else ""


def ssn_mask(f, ch="X"):
    s = _g(f, "ssn")
    tail = s[-4:] if len(s) >= 4 else s
    return _esc("%s%s%s-%s%s-%s" % (ch, ch, ch, ch, ch, tail))


BOXES = [
    ("1", "Wages, tips, other compensation", "w1"),
    ("2", "Federal income tax withheld", "w2"),
    ("3", "Social security wages", "w3"),
    ("4", "Social security tax withheld", "w4"),
    ("5", "Medicare wages and tips", "w5"),
    ("6", "Medicare tax withheld", "w6"),
]


def page(title, css, body, size="letter", margin="0.5in"):
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>%s</title>"
        "<style>@page{size:%s;margin:%s}"
        "*{box-sizing:border-box}body{margin:0;color:#111}"
        ".nw{white-space:nowrap}.pb{page-break-before:always}%s</style></head>"
        "<body>%s</body></html>" % (title, size, margin, css, body)
    )


def instructions_html(f, heading="Notice to Employee"):
    y = yr(f)
    return (
        "<h3>%s</h3>"
        "<p>Do you have to file? Refer to the Form 1040 instructions to determine whether you are required to "
        "file a tax return. Even if you don't have to file a tax return, you may be eligible for a refund if "
        "box 2 shows an amount or if you are eligible for any credit.</p>"
        "<p>Earned income credit (EIC). You may be able to take the EIC for %s if your adjusted gross income "
        "is less than a certain amount. Any EIC that is more than your tax liability is refunded to you, but "
        "only if you file a tax return.</p>"
        "<p>Clergy and religious workers. If you aren't subject to social security and Medicare taxes, see "
        "Pub. 517.</p>"
        "<p>Corrections. If your name, social security number (SSN), or address is incorrect, correct Copies "
        "B, C, and 2 and ask your employer to correct your employment record. Be sure to ask the employer to "
        "file Form W-2c with the Social Security Administration (SSA) to correct any name, SSN, or money amount "
        "error reported to the SSA on Form W-2.</p>"
        "<p>Box 12 codes: A - Uncollected social security or RRTA tax on tips; C - Taxable cost of group-term "
        "life insurance over $50,000; D - Elective deferrals to a section 401(k) plan; DD - Cost of "
        "employer-sponsored health coverage; E - Elective deferrals under a section 403(b) plan; H - Elective "
        "deferrals to a section 501(c)(18)(D) tax-exempt organization plan; W - Employer contributions to your "
        "Health Savings Account.</p>" % (heading, y)
    )


# ============================================================ 1. IRS grid
def t01_irs_grid_two_copies(f):
    css = """
body{font-family:Arial,Helvetica,sans-serif;font-size:9pt}
.copy{position:relative;margin:0 0 0.25in 0;padding-right:0.35in;height:4.9in}
.side{position:absolute;right:0;top:0;height:100%;width:0.3in;writing-mode:vertical-rl;
 transform:rotate(180deg);font-size:7.5pt;text-align:center;border-left:1px solid #000}
table.g{border-collapse:collapse;width:100%}
table.g td{border:1px solid #000;vertical-align:top;padding:2px 4px;height:0.42in}
.cap{font-size:6.5pt;display:block;margin-bottom:2px}
.cap b{margin-right:3px}
.v{font-family:'Courier New',monospace;font-size:10pt}
.shade{background:#eee}
.foot{font-size:7.5pt;display:flex;justify-content:space-between;margin-top:3px}
"""
    b12 = box12(f)
    b12cells = ""
    for i in range(4):
        s = "abcd"[i]
        if i < len(b12):
            _, c, a = b12[i]
        else:
            c, a = "", ""
        b12cells += "<div class='nw'><span class='cap' style='display:inline'><b>12%s</b></span> " \
                    "<span class='v'>%s</span> <span class='v'>%s</span></div>" % (s, c, a)

    def copy(label, side):
        return """
<div class='copy'>
<div class='side'>%(side)s</div>
<table class='g'>
<tr><td colspan='2' style='width:50%%'><span class='cap'><b>a</b>Employee's social security number</span><span class='v nw'>%(ssn)s</span></td>
<td colspan='2' class='shade'><span class='cap'>OMB No. 1545-0008</span></td></tr>
<tr><td colspan='2'><span class='cap'><b>b</b>Employer identification number (EIN)</span><span class='v nw'>%(ein)s</span></td>
<td><span class='cap'><b>1</b>Wages, tips, other compensation</span><span class='v'>%(w1)s</span></td>
<td><span class='cap'><b>2</b>Federal income tax withheld</span><span class='v'>%(w2)s</span></td></tr>
<tr><td colspan='2' rowspan='3'><span class='cap'><b>c</b>Employer's name, address, and ZIP code</span><span class='v'>%(emp)s</span></td>
<td><span class='cap'><b>3</b>Social security wages</span><span class='v'>%(w3)s</span></td>
<td><span class='cap'><b>4</b>Social security tax withheld</span><span class='v'>%(w4)s</span></td></tr>
<tr><td><span class='cap'><b>5</b>Medicare wages and tips</span><span class='v'>%(w5)s</span></td>
<td><span class='cap'><b>6</b>Medicare tax withheld</span><span class='v'>%(w6)s</span></td></tr>
<tr><td><span class='cap'><b>7</b>Social security tips</span></td><td><span class='cap'><b>8</b>Allocated tips</span></td></tr>
<tr><td colspan='2'><span class='cap'><b>d</b>Control number</span><span class='v nw'>%(ctl)s</span></td>
<td><span class='cap'><b>9</b></span></td><td><span class='cap'><b>10</b>Dependent care benefits</span></td></tr>
<tr><td style='width:28%%'><span class='cap'><b>e</b>Employee's first name and initial</span><span class='v nw'>%(first)s</span></td>
<td><span class='cap'>Last name</span><span class='v nw'>%(last)s</span> <span class='cap' style='display:inline'>Suff.</span></td>
<td><span class='cap'><b>11</b>Nonqualified plans</span></td><td rowspan='3'>%(b12)s</td></tr>
<tr><td colspan='2' rowspan='2'><span class='cap'><b>f</b>Employee's address and ZIP code</span><span class='v'>%(addr)s</span></td>
<td><span class='cap'><b>13</b>Statutory employee &#9744; Retirement plan &#9744; Third-party sick pay &#9744;</span></td></tr>
<tr><td><span class='cap'><b>14</b>Other</span></td></tr>
</table>
<table class='g' style='border-top:none'>
<tr><td style='width:8%%'><span class='cap'><b>15</b>State</span><span class='v'>%(st)s</span></td>
<td style='width:22%%'><span class='cap'>Employer's state ID number</span><span class='v nw'>%(stid)s</span></td>
<td><span class='cap'><b>16</b>State wages, tips, etc.</span><span class='v'>%(sw)s</span></td>
<td><span class='cap'><b>17</b>State income tax</span><span class='v'>%(stt)s</span></td>
<td><span class='cap'><b>18</b>Local wages, tips, etc.</span></td>
<td><span class='cap'><b>19</b>Local income tax</span></td>
<td><span class='cap'><b>20</b>Locality name</span></td></tr>
</table>
<div class='foot'><span><b style='font-size:11pt'>W-2</b> Wage and Tax Statement <b style='font-size:13pt'>%(y)s</b></span>
<span>%(label)s</span><span>Department of the Treasury&mdash;Internal Revenue Service</span></div>
</div>""" % dict(side=side, label=label, ssn=e(f, "ssn"), ein=e(f, "ein"), emp="<br>".join(emp_lines(f)),
                 w1=e(f, "w1"), w2=e(f, "w2"), w3=e(f, "w3"), w4=e(f, "w4"), w5=e(f, "w5"), w6=e(f, "w6"),
                 ctl=e(f, "control"), first=e(f, "first"), last=e(f, "last"), addr="<br>".join(addr_lines(f)),
                 b12=b12cells, st=e(f, "state1"), stid=e(f, "stid1"), sw=e(f, "sw1"), stt=e(f, "st1"), y=yr(f))

    body = copy("Copy B&mdash;To Be Filed With Employee's FEDERAL Tax Return.",
                "Copy B &mdash; To Be Filed With Employee's FEDERAL Tax Return") + \
        copy("Copy C&mdash;For EMPLOYEE'S RECORDS.", "Copy C &mdash; For EMPLOYEE'S RECORDS (See Notice to Employee)")
    return page("W-2 Copies B and C", css, body, margin="0.4in")


# ================================================= 2. three-up, value then caption
def t02_three_up_value_caption(f):
    css = """
body{font-family:Helvetica,Arial,sans-serif}
.cp{border:1.5px solid #000;height:3.25in;margin-bottom:0.08in;padding:0;position:relative;display:flex}
.vert{width:0.32in;border-right:1px solid #000;writing-mode:vertical-lr;transform:rotate(180deg);
 font-size:7pt;font-weight:bold;text-align:center;letter-spacing:1px}
.in{flex:1;display:grid;grid-template-columns:1.3fr 1fr 1fr;grid-auto-rows:minmax(0.36in,auto)}
.c{border-right:1px solid #000;border-bottom:1px solid #000;padding:3px 5px}
.c .val{font-size:9.5pt;font-weight:bold}
.c .cap{font-size:5.8pt;text-transform:uppercase;border-top:1px dotted #777;margin-top:2px;padding-top:1px}
.sp2{grid-row:span 2}.sp3{grid-row:span 3}.wide{grid-column:span 3}
"""
    nm = ("%s %s" % (_g(f, "first"), _g(f, "last"))).upper()
    b12 = box12(f)
    b12s = "&nbsp; ".join("%s %s" % (c, a) for _, c, a in b12) or "&nbsp;"
    y = yr(f)

    def cell(val, cap, cls=""):
        return "<div class='c %s'><div class='val'>%s</div><div class='cap'>%s</div></div>" % (cls, val or "&nbsp;", cap)

    def cp(lbl):
        return ("<div class='cp'><div class='vert'>%s %s W-2 &middot; %s</div><div class='in'>" % (y, "FORM", lbl) +
                cell("<span class='nw'>%s</span>" % e(f, "ssn"), "a Employee SSN") +
                cell(e(f, "w1"), "1 Wages, tips, other comp.") + cell(e(f, "w2"), "2 Federal income tax withheld") +
                cell("<span class='nw'>%s</span>" % e(f, "ein"), "b Employer ID no. (EIN)") +
                cell(e(f, "w3"), "3 Social security wages") + cell(e(f, "w4"), "4 Social security tax withheld") +
                cell("<br>".join(emp_lines(f)), "c Employer name, address and ZIP", "sp2") +
                cell(e(f, "w5"), "5 Medicare wages and tips") + cell(e(f, "w6"), "6 Medicare tax withheld") +
                cell(b12s, "12 See instructions for box 12") + cell("", "14 Other") +
                cell("<span class='nw'>%s</span>" % e(f, "control"), "d Control number") +
                cell(e(f, "state1") + " &nbsp; <span class='nw'>%s</span>" % e(f, "stid1"), "15 State / Employer state ID no.") +
                cell(e(f, "sw1"), "16 State wages, tips, etc.") +
                cell("<span class='nw'>%s</span><br>%s" % (_esc(nm), "<br>".join(addr_lines(f))),
                     "e/f Employee name, address and ZIP", "sp2") +
                cell(e(f, "st1"), "17 State income tax") + cell("", "18 Local wages, tips, etc.") +
                cell("", "19 Local income tax") + cell("", "20 Locality name") +
                "</div></div>")

    body = cp("COPY B &ndash; FEDERAL") + cp("COPY C &ndash; EMPLOYEE RECORDS") + cp("COPY 2 &ndash; STATE, CITY, OR LOCAL")
    return page("W-2 three-up", css, body, margin="0.35in")


# ================================================= 3. window envelope mailer + summary
def t03_window_envelope_mailer(f):
    css = """
body{font-family:Georgia,'Times New Roman',serif;font-size:10pt}
.ret{position:absolute;top:0.1in;left:0.1in;font-size:8.5pt;line-height:1.25}
.win{position:absolute;top:1.6in;left:0.55in;font-size:11pt;line-height:1.3;text-transform:uppercase;font-family:'Courier New',monospace}
.wrap{position:relative;height:3.3in;border-bottom:1px dashed #999}
.tag{position:absolute;top:0.1in;right:0.1in;text-align:right;font-size:8pt}
.tag b{font-size:16pt;display:block}
h2{font-size:12pt;margin:0.2in 0 6px}
table{border-collapse:collapse;width:100%}
td,th{border:1px solid #444;padding:3px 6px;font-size:9pt;vertical-align:top}
th{background:#ddd;text-align:left;font-size:8pt}
.sm{font-size:7pt;color:#333}
.pb p{font-size:9pt;line-height:1.35}
"""
    y = yr(f)
    rows = "".join("<tr><td class='sm'>Box %s</td><td>%s</td><td style='text-align:right'>%s</td></tr>"
                   % (n, c, money(e(f, k))) for n, c, k in BOXES)
    for s, c, a in box12(f):
        rows += "<tr><td class='sm'>Box 12%s</td><td>Code %s</td><td style='text-align:right'>%s</td></tr>" % (s, c, money(a))
    rows += "<tr><td class='sm'>Box 16</td><td>State wages (%s)</td><td style='text-align:right'>%s</td></tr>" % (e(f, "state1"), money(e(f, "sw1")))
    rows += "<tr><td class='sm'>Box 17</td><td>State income tax (%s)</td><td style='text-align:right'>%s</td></tr>" % (e(f, "state1"), money(e(f, "st1")))
    ctl = e(f, "control")
    body = """
<div class='wrap'>
<div class='ret'>%(emp)s</div>
<div class='tag'><b>W-2 %(y)s</b>IMPORTANT TAX RETURN DOCUMENT ENCLOSED</div>
<div class='win'>%(first)s %(last)s<br>%(addr)s</div>
</div>
<h2>Employee Wage and Tax Statement &ndash; Tax Year %(y)s</h2>
<table>
<tr><th style='width:34%%'>Social security number</th><th style='width:33%%'>Employer EIN</th><th>Control no.</th></tr>
<tr><td class='nw'>%(ssn)s</td><td class='nw'>%(ein)s</td><td class='nw'>%(ctl)s</td></tr>
<tr><th>State</th><th>Employer state ID</th><th>Copy</th></tr>
<tr><td>%(st)s</td><td class='nw'>%(stid)s</td><td>B, C and 2</td></tr>
</table>
<h2>Summary of earnings</h2>
<table><tr><th style='width:15%%'>Box</th><th>Description</th><th style='text-align:right;width:25%%'>Amount</th></tr>%(rows)s</table>
<p class='sm'>Processed by Harborline Payroll Services &middot; Statement ID W2-%(y)s-01 &middot; Page 1 of 2</p>
<div class='pb'>%(instr)s<p class='sm'>Page 2 of 2</p></div>
""" % dict(emp="<br>".join(emp_lines(f)), y=y, first=e(f, "first"), last=e(f, "last"),
           addr="<br>".join(addr_lines(f)), ssn=e(f, "ssn"), ein=e(f, "ein"), ctl=ctl or "&mdash;",
           st=e(f, "state1"), stid=e(f, "stid1"), rows=rows, instr=instructions_html(f, "Instructions for Employee"))
    return page("W-2 mailer", css, body, margin="0.5in")


# ================================================= 4. portal definition list
def t04_portal_definition_list(f):
    css = """
body{font-family:'Segoe UI',Roboto,Arial,sans-serif;font-size:10pt;color:#222}
.top{display:flex;justify-content:space-between;border-bottom:3px solid #2b5c8a;padding-bottom:6px;font-size:9pt}
.top .brand{font-weight:bold;font-size:13pt;color:#2b5c8a}
.crumb{font-size:8pt;color:#666;margin:6px 0 12px}
h1{font-size:15pt;margin:0 0 10px}
.panel{border:1px solid #ccd;border-radius:6px;padding:10px 14px;margin-bottom:12px}
.panel h2{font-size:10.5pt;margin:0 0 8px;color:#2b5c8a}
dl{display:grid;grid-template-columns:1.45in 1fr;gap:4px 12px;margin:0}
dt{color:#555}dd{margin:0;font-weight:600}
.two{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.foot{border-top:1px solid #ccc;margin-top:14px;padding-top:4px;font-size:7.5pt;color:#777;display:flex;justify-content:space-between}
"""
    y = yr(f)
    b12 = "".join("<dt>Box 12%s &ndash; code %s</dt><dd>%s</dd>" % (s, c, money(a)) for s, c, a in box12(f)) \
        or "<dt>Box 12</dt><dd>None reported</dd>"
    ctl = e(f, "control")
    ctl_html = "<dt>Control number</dt><dd class='nw'>%s</dd>" % ctl if ctl else ""
    body = """
<div class='top'><span class='brand'>WorkNest Employee Center</span><span>Home &nbsp;|&nbsp; Pay &nbsp;|&nbsp; Tax documents &nbsp;|&nbsp; Benefits &nbsp;|&nbsp; Sign out</span></div>
<div class='crumb'>Pay &rsaquo; Tax documents &rsaquo; W-2 %(y)s</div>
<h1>Form W-2 for tax year %(y)s</h1>
<div class='two'>
<div class='panel'><h2>Employee</h2><dl>
<dt>First name</dt><dd class='nw'>%(first)s</dd><dt>Last name</dt><dd class='nw'>%(last)s</dd>
<dt>Social security number</dt><dd class='nw'>%(ssn)s</dd>
<dt>Home address</dt><dd>%(addr)s</dd></dl></div>
<div class='panel'><h2>Employer</h2><dl>
<dt>Company</dt><dd>%(en)s</dd><dt>Address</dt><dd>%(eaddr)s</dd>
<dt>Federal EIN</dt><dd class='nw'>%(ein)s</dd>%(ctl)s</dl></div>
</div>
<div class='panel'><h2>Federal amounts</h2><dl>%(fed)s%(b12)s</dl></div>
<div class='panel'><h2>State amounts</h2><dl>
<dt>State</dt><dd>%(st)s</dd><dt>Employer state ID number</dt><dd class='nw'>%(stid)s</dd>
<dt>State wages, tips, etc.</dt><dd>%(sw)s</dd><dt>State income tax</dt><dd>%(stt)s</dd></dl></div>
<div class='foot'><span>This is a printable view of your W-2. Use the official copies B and C when filing.</span><span>Page 1 of 1</span></div>
""" % dict(y=y, first=e(f, "first"), last=e(f, "last"), ssn=e(f, "ssn"), addr="<br>".join(addr_lines(f)),
           en=e(f, "employer_name"), eaddr="<br>".join(emp_lines(f)[1:]), ein=e(f, "ein"), ctl=ctl_html,
           fed="".join("<dt>Box %s &ndash; %s</dt><dd>%s</dd>" % (n, c, money(e(f, k))) for n, c, k in BOXES),
           b12=b12, st=e(f, "state1"), stid=e(f, "stid1"), sw=money(e(f, "sw1")), stt=money(e(f, "st1")))
    return page("Employee Center W-2", css, body)


# ================================================= 5. dot leaders monospace
def t05_dot_leader_text(f):
    css = """
body{font-family:'Courier New',Courier,monospace;font-size:9.5pt}
pre{font-family:inherit;margin:0;line-height:1.35}
.hd{border-top:2px solid #000;border-bottom:2px solid #000;padding:4px 0;margin-bottom:8px}
"""
    W = 64

    def ln(label, val):
        dots = "." * max(3, W - len(label) - len(val) - 2)
        return "%s %s %s" % (label, dots, val)

    y = _g(f, "year") or "2025"
    L = []
    L.append(ln("Employee SSN", _g(f, "ssn")))
    L.append(ln("Employee name", "%s %s" % (_g(f, "first"), _g(f, "last"))))
    al = [x for x in _g(f, "address").split("\n") if x.strip()]
    for i, a in enumerate(al):
        L.append(ln("Employee address" if i == 0 else "  (cont.)", a))
    L.append("")
    L.append(ln("Employer FEIN", _g(f, "ein")))
    el = [x for x in _g(f, "employer").split("\n") if x.strip()]
    for i, a in enumerate(el):
        L.append(ln("Employer" if i == 0 else "  (cont.)", a))
    if _g(f, "control"):
        L.append(ln("Control number", _g(f, "control")))
    L.append("")
    for n, c, k in BOXES:
        L.append(ln("Box %-2s %s" % (n, c), _g(f, k)))
    for s, c, a in box12(f):
        L.append(ln("Box 12%s Code %s" % (s, c), a))
    L.append("")
    L.append(ln("Box 15 State", _g(f, "state1")))
    L.append(ln("Box 15 Employer state ID", _g(f, "stid1")))
    L.append(ln("Box 16 State wages", _g(f, "sw1")))
    L.append(ln("Box 17 State income tax", _g(f, "st1")))
    txt = _esc("\n".join(L))
    body = ("<pre class='hd'>%s\n%s</pre><pre>%s</pre><pre>\n\n%s\n%s</pre>" %
            (_esc("BLUE RIDGE PAYROLL BUREAU            W-2 REPRINT  TAX YEAR %s" % y),
             _esc("WAGE AND TAX STATEMENT - EMPLOYEE COPY"), txt,
             _esc("THIS INFORMATION IS BEING FURNISHED TO THE INTERNAL REVENUE SERVICE."),
             _esc("*** END OF STATEMENT ***")))
    return page("W-2 text reprint", css, body, margin="0.75in")


# ================================================= 6. boxes as rows
def t06_boxes_as_rows(f):
    css = """
body{font-family:Verdana,Arial,sans-serif;font-size:9pt}
h1{font-size:14pt;margin:0}.sub{color:#555;margin-bottom:10px}
table{border-collapse:collapse;width:100%;margin-bottom:12px}
th,td{padding:4px 8px;border-bottom:1px solid #ccc;text-align:left}
th{background:#1f3b4d;color:#fff;font-weight:normal;font-size:8pt;text-transform:uppercase}
td.amt{text-align:right;font-variant-numeric:tabular-nums}
tr:nth-child(even) td{background:#f4f7f9}
.hdr{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:2px solid #1f3b4d;padding-bottom:6px;margin-bottom:10px}
"""
    rows = [("a", "Employee's social security number", "<span class='nw'>%s</span>" % e(f, "ssn")),
            ("b", "Employer identification number (EIN)", "<span class='nw'>%s</span>" % e(f, "ein")),
            ("c", "Employer's name, address, and ZIP code", "<br>".join(emp_lines(f))),
            ("d", "Control number", "<span class='nw'>%s</span>" % e(f, "control")),
            ("e", "Employee's first name and initial", "<span class='nw'>%s</span>" % e(f, "first")),
            ("e", "Employee's last name", "<span class='nw'>%s</span>" % e(f, "last")),
            ("f", "Employee's address and ZIP code", "<br>".join(addr_lines(f)))]
    t1 = "".join("<tr><td style='width:8%%'>%s</td><td style='width:42%%'>%s</td><td>%s</td></tr>" % r for r in rows)
    am = [(n, c, money(e(f, k))) for n, c, k in BOXES]
    for s, c, a in box12(f):
        am.append(("12" + s, "Code " + c, money(a)))
    am += [("15", "State", e(f, "state1")), ("15", "Employer's state ID number", "<span class='nw'>%s</span>" % e(f, "stid1")),
           ("16", "State wages, tips, etc.", money(e(f, "sw1"))), ("17", "State income tax", money(e(f, "st1")))]
    t2 = "".join("<tr><td style='width:8%%'>%s</td><td>%s</td><td class='amt'>%s</td></tr>" % r for r in am)
    body = """<div class='hdr'><div><h1>Wage and Tax Statement</h1><div class='sub'>Form W-2 &middot; Tax year %s</div></div>
<div style='text-align:right;font-size:8pt'>Cedar &amp; Pine HR Cloud<br>Document center export</div></div>
<table><tr><th>Box</th><th>Identification</th><th>Value</th></tr>%s</table>
<table><tr><th>Box</th><th>Description</th><th style='text-align:right'>Amount</th></tr>%s</table>
<p style='font-size:7.5pt;color:#666'>Copy B &ndash; To be filed with employee's federal tax return. Copy C &ndash; For employee's records.</p>
""" % (yr(f), t1, t2)
    return page("W-2 boxes table", css, body)


# ================================================= 7. boxes as columns (landscape)
def t07_boxes_as_columns(f):
    css = """
body{font-family:Arial,sans-serif;font-size:8pt}
h1{font-size:12pt;margin:0 0 4px}
table{border-collapse:collapse;width:100%;margin-bottom:14px;table-layout:auto}
th{background:#e6e6e6;font-size:7pt;font-weight:bold;border:1px solid #888;padding:3px;vertical-align:bottom;text-align:left}
td{border:1px solid #888;padding:4px 3px;white-space:nowrap;font-size:8.5pt}
.note{font-size:7pt;color:#444}
"""
    b12 = box12(f)
    h1 = ["Tax Year", "Employee SSN", "First Name", "Last Name", "Street", "City/State/ZIP", "Control #"]
    al = addr_lines(f) + ["", ""]
    v1 = [yr(f), e(f, "ssn"), e(f, "first"), e(f, "last"), al[0], " ".join(al[1:]).strip(), e(f, "control")]
    h2 = ["FEIN", "Employer Name", "Employer Street", "Box 1 Wages", "Box 2 Fed W/H", "Box 3 SS Wages", "Box 4 SS Tax",
          "Box 5 Med Wages", "Box 6 Med Tax"]
    v2 = [e(f, "ein"), e(f, "employer_name"), e(f, "employer_street")] + [e(f, k) for _, _, k in BOXES]
    h3 = ["Box 12%s" % s.upper() for s, _, _ in b12] + ["St", "State ID", "Box 16 St Wages", "Box 17 St Tax"]
    v3 = ["%s %s" % (c, a) for _, c, a in b12] + [e(f, "state1"), e(f, "stid1"), e(f, "sw1"), e(f, "st1")]

    def tb(h, v):
        return "<table><tr>%s</tr><tr>%s</tr></table>" % ("".join("<th>%s</th>" % x for x in h),
                                                          "".join("<td>%s</td>" % x for x in v))
    el = emp_lines(f)
    body = ("<h1>W-2 Detail Report &ndash; Single Employee</h1><div class='note'>Generated by Ledgerly Payroll "
            "Reports &middot; Report W2-DTL &middot; Employer location: %s</div><br>" % (el[-1] if el else "")) + \
        tb(h1, v1) + tb(h2, v2) + tb(h3, v3) + \
        "<div class='note'>Amounts in US dollars. Report is for informational purposes; refer to the official Form W-2.</div>"
    return page("W-2 detail report", css, body, size="letter landscape", margin="0.4in")


# ================================================= 8. label-left, LAST, FIRST
def t08_label_left_lastfirst(f):
    css = """
body{font-family:'Times New Roman',serif;font-size:10.5pt}
h1{text-align:center;font-size:14pt;margin:0}.c{text-align:center;font-size:9pt;margin-bottom:14px}
table{width:100%;border-collapse:collapse;margin-bottom:10px}
td{padding:3px 6px;vertical-align:top}
td.l{width:2.4in;font-weight:bold}
.sec{font-variant:small-caps;font-size:11pt;border-bottom:1px solid #000;margin:12px 0 4px}
"""
    nm = "%s, %s" % (e(f, "last"), e(f, "first"))

    def r(l, v):
        return "<tr><td class='l'>%s:</td><td>%s</td></tr>" % (l, v)
    b12 = "".join(r("Box 12%s (code %s)" % (s, c), money(a)) for s, c, a in box12(f))
    body = "<h1>Statement of Wages and Taxes Withheld</h1><div class='c'>Calendar year %s &middot; Employee copy</div>" % yr(f) + \
        "<div class='sec'>Employee information</div><table>" + \
        r("Name", "<span class='nw'>%s</span>" % nm.upper()) + r("SSN", "<span class='nw'>%s</span>" % e(f, "ssn")) + \
        r("Address", "<br>".join(addr_lines(f))) + "</table>" + \
        "<div class='sec'>Employer information</div><table>" + \
        r("Employer", e(f, "employer_name")) + r("Address", "<br>".join(emp_lines(f)[1:])) + \
        r("EIN", "<span class='nw'>%s</span>" % e(f, "ein")) + \
        (r("Control no.", "<span class='nw'>%s</span>" % e(f, "control")) if _g(f, "control") else "") + "</table>" + \
        "<div class='sec'>Federal</div><table>" + \
        "".join(r("Wages (Box %s)" % n if n == "1" else "%s (Box %s)" % (c, n), money(e(f, k))) for n, c, k in BOXES) + b12 + \
        "</table><div class='sec'>State</div><table>" + \
        r("State / State ID", "%s &nbsp; <span class='nw'>%s</span>" % (e(f, "state1"), e(f, "stid1"))) + \
        r("State wages", money(e(f, "sw1"))) + r("State tax", money(e(f, "st1"))) + "</table>"
    return page("Statement of wages", css, body, margin="0.75in")


# ================================================= 9. fintech income verification (masked + full)
def t09_fintech_income_verification(f):
    css = """
body{font-family:Inter,Helvetica,Arial,sans-serif;font-size:9pt;color:#1b1b1b}
.bar{background:#0f2a2e;color:#fff;padding:10px 14px;display:flex;justify-content:space-between}
.bar b{font-size:13pt}
.meta{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:12px 0}
.meta div{background:#f1f5f5;padding:6px 8px;border-radius:4px}
.meta span{display:block;font-size:7pt;color:#5a6b6d;text-transform:uppercase;letter-spacing:.4px}
table{border-collapse:collapse;width:100%;margin-bottom:12px}
th{font-size:7pt;text-transform:uppercase;color:#5a6b6d;text-align:left;border-bottom:1px solid #9ab;padding:4px}
td{border-bottom:1px solid #e1e8e8;padding:4px;font-family:'Courier New',monospace;font-size:8.5pt}
h3{font-size:10pt;margin:14px 0 4px}
.foot{font-size:7pt;color:#777;border-top:1px solid #ccc;padding-top:4px;margin-top:10px}
"""
    y = yr(f)
    al = addr_lines(f)
    data = [("employee.name.first", e(f, "first"), "W-2 box e"), ("employee.name.last", e(f, "last"), "W-2 box e"),
            ("employee.ssn", e(f, "ssn"), "W-2 box a")]
    for i, a in enumerate(al):
        data.append(("employee.address.line%d" % (i + 1), a, "W-2 box f"))
    data += [("employer.name", e(f, "employer_name"), "W-2 box c"), ("employer.address.street", e(f, "employer_street"), "W-2 box c"),
             ("employer.ein", e(f, "ein"), "W-2 box b")]
    if _g(f, "control"):
        data.append(("document.control_number", e(f, "control"), "W-2 box d"))
    for n, c, k in BOXES:
        data.append(("box_%s.%s" % (n, c.lower().replace(",", "").replace(" ", "_")), e(f, k), "W-2 box %s" % n))
    for s, c, a in box12(f):
        data.append(("box_12%s.code" % s, c, "W-2 box 12%s" % s))
        data.append(("box_12%s.amount" % s, a, "W-2 box 12%s" % s))
    data += [("state[0].code", e(f, "state1"), "W-2 box 15"), ("state[0].employer_state_id", e(f, "stid1"), "W-2 box 15"),
             ("state[0].wages", e(f, "sw1"), "W-2 box 16"), ("state[0].income_tax", e(f, "st1"), "W-2 box 17")]
    rows = "".join("<tr><td>%s</td><td class='nw'>%s</td><td>%s</td></tr>" % d for d in data)
    body = """<div class='bar'><b>Clearpath Verify &middot; Income Verification Report</b><span>Source: Form W-2 (%(y)s)</span></div>
<div class='meta'><div><span>Applicant</span>%(first)s %(last)s</div><div><span>SSN</span>%(mask)s</div>
<div><span>Employer</span>%(en)s</div><div><span>Annual gross (Box 1)</span>%(w1)s</div>
<div><span>Federal W/H</span>%(w2)s</div><div><span>Document status</span>Parsed &middot; verified</div>
<div><span>Tax year</span>%(y)s</div><div><span>Confidence</span>0.98</div></div>
<h3>Extracted fields</h3>
<table><tr><th style='width:40%%'>Field</th><th>Value</th><th>Source</th></tr>%(rows)s</table>
<div class='foot'>This report was generated from a document uploaded by the applicant. Values are reproduced as extracted. Report ID IV-%(y)s-0001 &middot; Page 1</div>
""" % dict(y=y, first=e(f, "first"), last=e(f, "last"), mask=ssn_mask(f, "*"), en=e(f, "employer_name"),
           w1=money(e(f, "w1")), w2=money(e(f, "w2")), rows=rows)
    return page("Income Verification Report", css, body, margin="0.45in")


# ================================================= 10. dashboard cards (masked header)
def t10_dashboard_cards(f):
    css = """
body{font-family:'Helvetica Neue',Arial,sans-serif;font-size:9pt;background:#fff}
.head{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.head h1{font-size:16pt;margin:0}.pill{border:1px solid #6a4;color:#384;border-radius:10px;padding:2px 8px;font-size:8pt}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:10px}
.card{border:1px solid #d6d6e0;border-radius:6px;padding:8px 10px}
.card .big{font-size:14pt;font-weight:600}
.card .lab{font-size:7.5pt;color:#667;margin-top:2px}
.cols{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}
.box{border:1px solid #d6d6e0;border-radius:6px;padding:8px 10px}
.box h4{margin:0 0 6px;font-size:8.5pt;text-transform:uppercase;color:#556;letter-spacing:.5px}
.kv{display:flex;justify-content:space-between;border-bottom:1px dashed #e3e3ea;padding:2px 0}
.kv span:first-child{color:#667}
.ftr{margin-top:12px;font-size:7pt;color:#889;text-align:center}
"""
    y = yr(f)

    def card(v, l):
        return "<div class='card'><div class='big'>%s</div><div class='lab'>%s</div></div>" % (v, l)

    def kv(k, v):
        return "<div class='kv'><span>%s</span><span class='nw'>%s</span></div>" % (k, v)
    cards = "".join(card(money(e(f, k)), "Box %s &middot; %s" % (n, c)) for n, c, k in BOXES)
    b12 = "".join(kv("12%s &ndash; %s" % (s, c), money(a)) for s, c, a in box12(f)) or kv("Box 12", "&mdash;")
    body = """<div class='head'><div><h1>Year-end tax summary %(y)s</h1><div style='color:#667'>%(first)s %(last)s &middot; SSN %(mask)s</div></div>
<span class='pill'>W-2 available</span></div>
<div class='grid'>%(cards)s</div>
<div class='cols'>
<div class='box'><h4>Form details</h4>%(k1)s%(k2)s%(k3)s%(k4)s%(k5)s</div>
<div class='box'><h4>Mailing address on file</h4><div>%(first)s %(last)s<br>%(addr)s</div><br><h4>Employer</h4><div>%(emp)s</div></div>
<div class='box'><h4>State &amp; other</h4>%(s1)s%(s2)s%(s3)s%(s4)s%(b12)s</div>
</div>
<div class='ftr'>Brightwage Pay &middot; Employee dashboard &middot; printed view &middot; amounts in USD</div>
""" % dict(y=y, first=e(f, "first"), last=e(f, "last"), mask=ssn_mask(f, "X"), cards=cards,
           k1=kv("Employee SSN", e(f, "ssn")), k2=kv("Employer EIN", e(f, "ein")),
           k3=kv("Control number", e(f, "control") or "&mdash;"), k4=kv("Tax year", y), k5=kv("Form", "W-2"),
           addr="<br>".join(addr_lines(f)), emp="<br>".join(emp_lines(f)),
           s1=kv("State", e(f, "state1")), s2=kv("State ID", e(f, "stid1")), s3=kv("State wages", money(e(f, "sw1"))),
           s4=kv("State tax", money(e(f, "st1"))), b12=b12)
    return page("Year-end tax summary", css, body, margin="0.45in")


# ================================================= 11. tax software worksheet (same cell)
def t11_tax_software_worksheet(f):
    css = """
body{font-family:Tahoma,Arial,sans-serif;font-size:9pt}
.tb{background:#dfe6ee;border:1px solid #8aa;padding:4px 8px;display:flex;justify-content:space-between;font-size:8pt}
h2{font-size:12pt;margin:8px 0}
table{border-collapse:collapse;width:100%;margin-bottom:8px}
td{border:1px solid #9ab;padding:5px 6px;vertical-align:top}
td b{color:#335;font-weight:bold;margin-right:4px}
.q{font-size:8pt;margin:4px 0;color:#333}
"""
    y = yr(f)
    b12 = box12(f)
    b12c = "".join("<td><b>12%s Code:</b> %s &nbsp; <b>Amt:</b> %s</td>" % (s.upper(), c, a) for s, c, a in b12)
    if not b12c:
        b12c = "<td><b>12 Codes:</b> (none)</td>"
    al = addr_lines(f)
    body = """<div class='tb'><span>TaxDesk Pro %(y)s &middot; Client return &middot; Federal &rsaquo; Income &rsaquo; W-2</span><span>Worksheet 1 of 1</span></div>
<h2>Form W-2 Input Worksheet &ndash; Taxpayer</h2>
<table>
<tr><td style='width:50%%'><b>Employee SSN:</b> <span class='nw'>%(ssn)s</span></td><td><b>FEIN:</b> <span class='nw'>%(ein)s</span></td></tr>
<tr><td><b>Employee first name:</b> <span class='nw'>%(first)s</span></td><td><b>Employer name:</b> %(en)s</td></tr>
<tr><td><b>Employee last name:</b> <span class='nw'>%(last)s</span></td><td><b>Employer street:</b> %(es)s</td></tr>
<tr><td><b>Street:</b> %(a0)s</td><td><b>Employer city/st/zip:</b> %(ec)s</td></tr>
<tr><td><b>City, State ZIP:</b> %(a1)s</td><td><b>Control no.:</b> <span class='nw'>%(ctl)s</span></td></tr>
</table>
<table>
<tr><td><b>Box 1 Wages:</b> %(w1)s</td><td><b>Box 2 Fed W/H:</b> %(w2)s</td></tr>
<tr><td><b>Box 3 SS wages:</b> %(w3)s</td><td><b>Box 4 SS W/H:</b> %(w4)s</td></tr>
<tr><td><b>Box 5 Medicare wages:</b> %(w5)s</td><td><b>Box 6 Medicare W/H:</b> %(w6)s</td></tr>
</table>
<table><tr>%(b12)s</tr></table>
<table><tr><td><b>15 St:</b> %(st)s</td><td><b>15 Emp. state ID:</b> <span class='nw'>%(stid)s</span></td>
<td><b>16 St wages:</b> %(sw)s</td><td><b>17 St tax:</b> %(stt)s</td></tr></table>
<div class='q'>[ ] Statutory employee &nbsp; [ ] Retirement plan &nbsp; [ ] Third-party sick pay &nbsp; [ ] Corrected W-2</div>
<div class='q'>Preparer note: verify amounts against client's Copy B before e-file.</div>
""" % dict(y=y, ssn=e(f, "ssn"), ein=e(f, "ein"), first=e(f, "first"), last=e(f, "last"),
           en=e(f, "employer_name"), es=e(f, "employer_street"), ec=(emp_lines(f) + [""] * 3)[2],
           a0=(al + ["", ""])[0], a1="<br>".join(al[1:]), ctl=e(f, "control"),
           w1=money(e(f, "w1")), w2=money(e(f, "w2")), w3=money(e(f, "w3")), w4=money(e(f, "w4")),
           w5=money(e(f, "w5")), w6=money(e(f, "w6")), b12=b12c, st=e(f, "state1"), stid=e(f, "stid1"),
           sw=money(e(f, "sw1")), stt=money(e(f, "st1")))
    return page("W-2 Input Worksheet", css, body)


# ================================================= 12. side by side, label above, rotated side text
def t12_side_by_side_rotated(f):
    css = """
body{font-family:Arial,sans-serif;font-size:9pt}
.wrap{position:relative;padding-left:0.5in}
.rot{position:absolute;left:0;top:0;width:0.4in;height:9.5in;writing-mode:vertical-rl;transform:rotate(180deg);
 font-size:20pt;font-weight:bold;color:#bbb;letter-spacing:6px;text-align:center}
.pair{display:flex;gap:12px;margin-bottom:12px}
.blk{flex:1;border:1px solid #333;padding:8px}
.blk h3{margin:0 0 6px;font-size:9pt;background:#333;color:#fff;padding:2px 6px}
.f{margin-bottom:6px}.f .l{font-size:7pt;color:#555;text-transform:uppercase}.f .v{font-size:10pt}
.amts{display:grid;grid-template-columns:repeat(3,1fr);border-top:1px solid #333;border-left:1px solid #333}
.amts .f{border-right:1px solid #333;border-bottom:1px solid #333;padding:5px;margin:0}
h1{font-size:13pt;margin:0 0 10px}
"""

    def fld(l, v):
        return "<div class='f'><div class='l'>%s</div><div class='v'>%s</div></div>" % (l, v or "&nbsp;")
    b12 = "".join(fld("Box 12%s code / amount" % s, "%s &nbsp; %s" % (c, money(a))) for s, c, a in box12(f))
    body = """<div class='wrap'><div class='rot'>EMPLOYEE REFERENCE COPY</div>
<h1>W-2 Wage &amp; Tax Statement %(y)s</h1>
<div class='pair'>
<div class='blk'><h3>EMPLOYER</h3>%(en)s%(ea)s%(ein)s%(ctl)s</div>
<div class='blk'><h3>EMPLOYEE</h3><div style='display:flex;gap:16px'>%(fn)s%(ln)s</div>%(ssn)s%(ad)s</div>
</div>
<div class='amts'>%(amts)s%(b12)s%(st)s%(stid)s%(sw)s%(stt)s</div>
<p style='font-size:7.5pt;color:#555'>Issued by Northgate Workforce Solutions on behalf of the employer named above.</p>
</div>""" % dict(y=yr(f), en=fld("Employer name", e(f, "employer_name")),
                 ea=fld("Employer address", "<br>".join(emp_lines(f)[1:])),
                 ein=fld("Employer identification number", "<span class='nw'>%s</span>" % e(f, "ein")),
                 ctl=fld("Control number", "<span class='nw'>%s</span>" % e(f, "control")),
                 fn=fld("First name", "<span class='nw'>%s</span>" % e(f, "first")),
                 ln=fld("Last name", "<span class='nw'>%s</span>" % e(f, "last")),
                 ssn=fld("Social security number", "<span class='nw'>%s</span>" % e(f, "ssn")),
                 ad=fld("Address", "<br>".join(addr_lines(f))),
                 amts="".join(fld("%s. %s" % (n, c), money(e(f, k))) for n, c, k in BOXES), b12=b12,
                 st=fld("15. State", e(f, "state1")),
                 stid=fld("15. Employer's state ID no.", "<span class='nw'>%s</span>" % e(f, "stid1")),
                 sw=fld("16. State wages", money(e(f, "sw1"))), stt=fld("17. State income tax", money(e(f, "st1"))))
    return page("W-2 reference copy", css, body)


# ================================================= 13. ALL CAPS, label and value in same cell with dash
def t13_caps_same_cell_dash(f):
    css = """
body{font-family:'Arial Narrow',Arial,sans-serif;font-size:9pt;text-transform:uppercase}
.hd{text-align:center;border:2px solid #000;padding:4px;font-weight:bold;font-size:11pt;margin-bottom:6px}
table{border-collapse:collapse;width:100%;margin-bottom:6px}
td{border:1px solid #000;padding:4px 5px}
.ft{display:flex;justify-content:space-between;font-size:7pt;margin-top:6px}
"""
    nm = "%s %s" % (e(f, "first"), e(f, "last"))
    al = addr_lines(f)

    def c(l, v, cs=1):
        return "<td colspan='%d'>%s &mdash; <span class='nw'>%s</span></td>" % (cs, l, v)
    b12 = box12(f)
    b12r = "".join(c("BOX 12%s" % s.upper(), "%s %s" % (cc, a)) for s, cc, a in b12)
    body = "<div class='hd'>%s FORM W-2 &nbsp; WAGE AND TAX STATEMENT &nbsp; EMPLOYEE COPY</div>" % yr(f) + \
        "<table><tr>%s%s</tr><tr>%s%s</tr><tr>%s</tr><tr>%s</tr></table>" % (
            c("EMP. SSN", e(f, "ssn")), c("EMP. ID (EIN)", e(f, "ein")),
            c("EMPLOYEE", nm), c("CTRL NO.", e(f, "control")),
            "<td colspan='2'>EMPLOYEE ADDR &mdash; %s</td>" % " / ".join("<span class='nw'>%s</span>" % a for a in al),
            "<td colspan='2'>EMPLOYER &mdash; %s</td>" % " / ".join("<span class='nw'>%s</span>" % a for a in emp_lines(f))) + \
        "<table><tr>%s%s%s</tr><tr>%s%s%s</tr></table>" % tuple(
            c("BOX %s %s" % (n, l), e(f, k)) for n, l, k in
            [("1", "WAGES", "w1"), ("3", "SS WAGES", "w3"), ("5", "MEDICARE WAGES", "w5"),
             ("2", "FED W/H", "w2"), ("4", "SS TAX", "w4"), ("6", "MEDICARE TAX", "w6")]) + \
        ("<table><tr>%s</tr></table>" % b12r if b12r else "") + \
        "<table><tr>%s%s%s%s</tr></table>" % (c("ST", e(f, "state1")), c("ST ID", e(f, "stid1")),
                                              c("ST WAGES", e(f, "sw1")), c("ST TAX", e(f, "st1"))) + \
        "<div class='ft'><span>KEEP FOR YOUR RECORDS</span><span>PRINTED BY SUMMIT PAYDATA</span><span>PG 1/1</span></div>"
    body = body * 1
    # second, cut-line copy
    body = body + "<div style='border-top:1px dashed #000;margin:14px 0'></div>" + body.replace("EMPLOYEE COPY", "COPY 2 STATE FILING")
    return page("W-2 employee copy", css, body)


# ================================================= 14. stacked blocks, abbreviated labels, summary + instructions
def t14_stacked_summary_instructions(f):
    css = """
body{font-family:Calibri,Arial,sans-serif;font-size:10pt}
.hdr{display:flex;justify-content:space-between;font-size:8pt;color:#555;border-bottom:1px solid #aaa;margin-bottom:8px}
.blk{border-left:4px solid #8a5a2b;padding:4px 10px;margin-bottom:10px;background:#faf6f1}
.blk h3{margin:0 0 4px;font-size:10pt}
.r{display:flex;gap:6px}.r .l{min-width:1.3in;color:#555}
table{border-collapse:collapse;width:100%}
td,th{padding:3px 6px;border:1px solid #ccc;font-size:9pt}
th{background:#efe6dc;text-align:left}
.amt{text-align:right}
.pb p{font-size:9pt}
.ftr{position:fixed;bottom:0;left:0;right:0;font-size:7pt;color:#777;text-align:center}
"""
    y = yr(f)

    def r(l, v):
        return "<div class='r'><span class='l'>%s</span><span class='nw'>%s</span></div>" % (l, v)
    labels = {"1": "Wages (Box 1)", "2": "Fed W/H (Box 2)", "3": "SS wages (Box 3)", "4": "SS tax (Box 4)",
              "5": "Medicare wages (Box 5)", "6": "Medicare tax (Box 6)"}
    rows = "".join("<tr><td>%s</td><td class='amt'>%s</td></tr>" % (labels[n], money(e(f, k))) for n, _, k in BOXES)
    rows += "".join("<tr><td>Box 12%s (%s)</td><td class='amt'>%s</td></tr>" % (s, c, money(a)) for s, c, a in box12(f))
    rows += "<tr><td>St wages (Box 16)</td><td class='amt'>%s</td></tr><tr><td>St tax (Box 17)</td><td class='amt'>%s</td></tr>" % (
        money(e(f, "sw1")), money(e(f, "st1")))
    al = addr_lines(f)
    body = """<div class='ftr'>Oakfield Payroll Partners &middot; W-2 statement &middot; tax year %(y)s</div>
<div class='hdr'><span>W-2 Statement &ndash; %(y)s</span><span>Employee copy</span></div>
<div class='blk'><h3>Employer</h3>%(en)s%(ea)s%(ein)s%(stid)s%(ctl)s</div>
<div class='blk'><h3>Employee</h3>%(nm)s%(a0)s%(a1)s%(ssn)s</div>
<h3>Summary of earnings and withholding</h3>
<table><tr><th>Item</th><th class='amt'>Amount</th></tr>%(rows)s</table>
<div class='pb'>%(instr)s
<h3>Where to report on your tax return</h3>
<table><tr><th>W-2 box</th><th>Form 1040 line</th></tr>
<tr><td>Box 1</td><td>Line 1a</td></tr><tr><td>Box 2</td><td>Line 25a</td></tr>
<tr><td>Box 12 code D, E</td><td>Retirement contributions (see instructions)</td></tr>
<tr><td>Box 17</td><td>Schedule A, line 5a (if itemizing)</td></tr></table></div>
""" % dict(y=y, en=r("Name", e(f, "employer_name")), ea=r("Address", ", ".join(emp_lines(f)[1:])),
           ein=r("FEIN", e(f, "ein")), stid=r("St. ID (%s)" % e(f, "state1"), e(f, "stid1")),
           ctl=r("Ctrl #", e(f, "control")) if _g(f, "control") else "",
           nm=r("Name", "%s %s" % (e(f, "first"), e(f, "last"))), a0=r("Street", (al + [""])[0]),
           a1=r("City/St/ZIP", " ".join(al[1:])), ssn=r("SSN", e(f, "ssn")), rows=rows,
           instr=instructions_html(f, "Instructions for employee"))
    return page("W-2 statement and instructions", css, body, margin="0.6in")


# ================================================= 15. bank export, LAST, FIRST, colon labels in records
def t15_bank_income_export(f):
    css = """
body{font-family:'Lucida Console','Courier New',monospace;font-size:8.5pt}
.h{border-bottom:1px solid #000;padding-bottom:4px;margin-bottom:6px;display:flex;justify-content:space-between}
table{border-collapse:collapse;width:100%}
th{border-bottom:1px solid #000;text-align:left;padding:3px;font-weight:bold}
td{padding:3px;border-bottom:1px dotted #aaa;vertical-align:top}
.s{margin-top:10px;font-size:7.5pt}
"""
    y = yr(f)
    al = addr_lines(f)
    recs = [("INC-01", "BORROWER", "%s, %s" % (e(f, "last"), e(f, "first"))),
            ("INC-02", "BORROWER TIN", e(f, "ssn")),
            ("INC-03", "BORROWER ADDR 1", (al + [""])[0]),
            ("INC-04", "BORROWER ADDR 2", " ".join(al[1:])),
            ("INC-05", "EMPLOYER", e(f, "employer_name")),
            ("INC-06", "EMPLOYER ADDR", " / ".join(emp_lines(f)[1:])),
            ("INC-07", "EMPLOYER TIN", e(f, "ein")),
            ("INC-08", "W2 CTRL", e(f, "control") or "N/A")]
    i = 9
    for n, c, k in BOXES:
        recs.append(("INC-%02d" % i, "W2 BOX %s" % n, money(e(f, k)))); i += 1
    for s, c, a in box12(f):
        recs.append(("INC-%02d" % i, "W2 BOX 12%s %s" % (s.upper(), c), money(a))); i += 1
    recs += [("INC-%02d" % i, "W2 BOX 15 ST/ID", "%s %s" % (e(f, "state1"), e(f, "stid1"))),
             ("INC-%02d" % (i + 1), "W2 BOX 16", money(e(f, "sw1"))), ("INC-%02d" % (i + 2), "W2 BOX 17", money(e(f, "st1")))]
    rows = "".join("<tr><td>%s</td><td>%s</td><td class='nw'>%s</td><td>W-2 %s</td></tr>" % (a, b, c, y) for a, b, c in recs)
    body = """<div class='h'><span>FIRST HARBOR SAVINGS &ndash; MORTGAGE INCOME DOCUMENTATION EXPORT</span><span>RUN DATE: %(y)s-YE</span></div>
<div>LOAN FILE: (UNASSIGNED) &nbsp; DOC TYPE: IRS FORM W-2 &nbsp; TAX YEAR: %(y)s</div><br>
<table><tr><th>REC</th><th>FIELD</th><th>VALUE</th><th>SOURCE</th></tr>%(rows)s</table>
<div class='s'>Annualized qualifying income (Box 5 basis): %(w5)s. Underwriter must reconcile against paystubs. END OF EXPORT.</div>
""" % dict(y=y, rows=rows, w5=money(e(f, "w5")))
    return page("Income documentation export", css, body)


# ================================================= 16. reprint boxes with colon labels + page 2 instructions
def t16_reprint_colon_boxes(f):
    css = """
body{font-family:'Trebuchet MS',Arial,sans-serif;font-size:9.5pt}
.top{display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid #444;padding-bottom:6px}
.yr{font-size:34pt;font-weight:bold;color:#fff;-webkit-text-stroke:1.2px #333;letter-spacing:2px}
.ttl{font-size:13pt;font-weight:bold}
.g{display:grid;grid-template-columns:1fr 1fr;gap:0;border:1px solid #444;margin-top:10px}
.g div{border:1px solid #bbb;padding:5px 8px}
.g .full{grid-column:span 2}
.g b{font-weight:600}
.mark{font-size:8pt;border:1px solid #c00;color:#c00;display:inline-block;padding:1px 6px;transform:rotate(-4deg)}
.foot{margin-top:10px;font-size:7.5pt;color:#555;display:flex;justify-content:space-between}
.pb p{font-size:9pt}
"""
    y = yr(f)
    al = addr_lines(f)

    def d(l, v, full=False):
        return "<div%s><b>%s:</b> <span class='nw'>%s</span></div>" % (" class='full'" if full else "", l, v)
    cells = [d("SSN", e(f, "ssn")), d("EIN", e(f, "ein")),
             d("Employee first name", e(f, "first")), d("Employee last name", e(f, "last")),
             "<div class='full'><b>Employee address:</b> %s</div>" % ", ".join("<span class='nw'>%s</span>" % a for a in al),
             "<div class='full'><b>Employer:</b> %s</div>" % ", ".join("<span class='nw'>%s</span>" % a for a in emp_lines(f)),
             d("Control number", e(f, "control")), d("Form", "W-2 (reprint)")]
    for n, c, k in BOXES:
        cells.append(d("Box %s - %s" % (n, c), money(e(f, k))))
    for s, c, a in box12(f):
        cells.append(d("Box 12%s - Code %s" % (s, c), money(a)))
    if len(box12(f)) % 2:
        cells.append("<div>&nbsp;</div>")
    cells += [d("Box 15 - State", e(f, "state1")), d("Box 15 - Employer state ID", e(f, "stid1")),
              d("Box 16 - State wages", money(e(f, "sw1"))), d("Box 17 - State income tax", money(e(f, "st1")))]
    body = """<div class='top'><div><div class='ttl'>Wage and Tax Statement</div><div>Reprinted at employee request &middot; Riverbend Payroll Co-op</div></div>
<span class='mark'>DUPLICATE</span><div class='yr'>%(y)s</div></div>
<div class='g'>%(cells)s</div>
<div class='foot'><span>This reprint contains the same information as the original Form W-2 furnished to you.</span><span>Page 1 of 2</span></div>
<div class='pb'>%(instr)s<div class='foot'><span>Riverbend Payroll Co-op &middot; Questions? Contact your payroll administrator.</span><span>Page 2 of 2</span></div></div>
""" % dict(y=y, cells="".join(cells), instr=instructions_html(f))
    return page("W-2 reprint", css, body)


TEMPLATES = [
    t01_irs_grid_two_copies,
    t02_three_up_value_caption,
    t03_window_envelope_mailer,
    t04_portal_definition_list,
    t05_dot_leader_text,
    t06_boxes_as_rows,
    t07_boxes_as_columns,
    t08_label_left_lastfirst,
    t09_fintech_income_verification,
    t10_dashboard_cards,
    t11_tax_software_worksheet,
    t12_side_by_side_rotated,
    t13_caps_same_cell_dash,
    t14_stacked_summary_instructions,
    t15_bank_income_export,
    t16_reprint_colon_boxes,
]
