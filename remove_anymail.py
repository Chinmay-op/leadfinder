import re

def clean_file(path, replacements):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        return
    
    for pat, rep in replacements:
        content = re.sub(pat, rep, content)
        
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

clean_file('static/index.html', [
    (r'<div class=\"anymail-badge\"[^>]*>[\s\S]*?</button>\s*</div>\n', ''),
    (r'\s*<div class=\"toggle-row\" id=\"toggle-anymail-row\">[\s\S]*?<span class=\"toggle-label\">AnyMail Finder email</span>\s*</div>\n', ''),
    (r'\s*<button class=\"btn btn-sm amber-left\" id=\"btn-anymail\">.*?AnyMail</button>', '')
])

clean_file('static/style.css', [
    (r'\n\.anymail-badge \{[\s\S]*?\.anymail-refresh:hover \{[^}]*\}\n', '')
])

clean_file('static/app.js', [
    (r'\s*enableAnymail:\s*true,', ''),
    (r'\s*anymailQuota:\s*null,', ''),
    (r'\s*enrichAnymail\(\)\s*\{[^\}]*\},\n?', ''),
    (r'\s*anymailStatus\(\)\s*\{[^\}]*\},\n?', ''),
    (r'\s*// Stage 2A: AnyMail\s*if\s*\(state\.enableAnymail\)\s*\{\s*stages\.push\(async\s*\(\)\s*=>\s*\{\s*await\s*API\.enrichAnymail\(\);\s*\}\);\s*\}\n?', ''),
    (r' \|\| \(lead\.anymail_email && lead\.anymail_email\.trim\(\)\)', ''),
    (r'lead\.anymail_email \|\| ', ''),
    (r' \|\| l\.anymail_email', ''),
    (r'\s*if\s*\(lead\.anymail_confidence\)\s*\{[\s\S]*?\}', ''),
    (r'\s*bindToggle\(\'toggle-anymail\',\s*\'enableAnymail\'\);', ''),
    (r'\s*document\.getElementById\(\'btn-anymail\'\)\.addEventListener\([\s\S]*?\}\);\n?', ''),
    (r'\n// ── AnyMail Quota ──[\s\S]*?refreshAnymailQuota\(\);\n', '\n'),
    (r'\s*refreshAnymailQuota\(\);\n?', '\n')
])

clean_file('app.py', [
    (r'from anymail_finder import run_anymail_enrichment, get_account_status as get_anymail_status\n?', ''),
    (r'@app\.post\("/api/enrich/anymail"\)\nasync def enrich_anymail_endpoint\(\):[\s\S]*?await loop\.run_in_executor\(None, run_anymail_enrichment, state\)\n\n?', ''),
    (r'@app\.get\("/api/anymail/status"\)\nasync def anymail_status_endpoint\(\):[\s\S]*?return result\n\n?', '')
])

clean_file('models/business.py', [
    (r'\s*anymail_email:\s*Optional\[str\]\s*=\s*None', ''),
    (r'\s*anymail_confidence:\s*Optional\[float\]\s*=\s*None', '')
])

clean_file('models/contact.py', [
    (r'\s*\|\s*\"anymail\"', '')
])

clean_file('export.py', [
    (r'\"anymail_co\":\s*\d+,?\s*', '')
])
