import pathlib

filepath = pathlib.Path(rC:\py_dev\mko_bazuna\.ai\audit\99-validation\06-pii-consent-validated-findings.md)
content = filepath.read_text(encoding=utf-8)

repl_data = [
    {
        label: PII-003 evidence,
        old: '''- Consent model uses 3 distinct DateTimeField states: \consent_given_at\ (set at DECLINE), \consent_revoked_at\ (set at WITHDRAW), \ccount_deleted_at\ (set at DELETE). See \pps/users/models.py:34-37\.
- All 3 actions are reachable via distinct URL endpoints: \consent_decline\ (\/consent/decline/\), \consent_withdraw\ (\/consent/withdraw/\), \consent_accept\ (\/consent/accept/\). See \pps/users/urls.py:17-25\.
- \consent_decline()\ (\iews/consent.py:187-220\) sets \consent_given_at\ but does NOT hard-delete or soft-delete ads — buyer can still browse anonymously (spec-compliant).
- \consent_withdraw()\ (\iews/consent.py:105-145\) triggers \withdraw_consent()\ → hard token deletion + (intended) telegram_id NULLing + (pending) ad soft-delete.
- No re-grant consent user story found in \docs/04-user-stories/\ (finding cited one — stale).
- Spec Decision F explicitly defines: DECLINE = reject banner; WITHDRAW = erase PII from existing ad; DELETE = remove account entirely.
''',
        new: '''- Consent model uses distinct DateTimeField states: \consent_given_at\ (set at ACCEPT — \models.py:74\), \consent_revoked_at\ (set at WITHDRAW — \models.py:79\), \deleted_at\ (set at DELETE — \models.py:69\). No \ccount_deleted_at\ field exists. See \pps/users/models.py:68-83\.
- All 3 actions are reachable via distinct URL endpoints: \consent_accept\ (\/consent/accept/\), \consent_decline\ (\/consent/decline/\), \consent_withdraw\ (\/consent/withdraw/\). See \pps/users/urls.py:8-13\.
- \consent_decline()\ (\iews/consent.py:67-93\) sets \is_declined=True\ + \ds_auto_publish=False\ — does NOT set \consent_revoked_at\, does NOT null PII, does NOT soft-delete ads (spec-compliant: buyer can still browse anonymously).
- \consent_withdraw()\ (\iews/consent.py:97-123\) triggers \withdraw_consent()\ → deletes ALL LoginTokens by telegram_id (\deletion.py:132\) + nulls \	elegram_id\/\username\ (\deletion.py:148-154\) + soft-deletes ads (\deletion.py:180\). Crashes on \User.telegram_id\ NOT NULL (PII-001).
- No re-grant consent user story found in \docs/04-user-stories/\ (finding cited one — stale).
- Spec Decision F (technical-specification.md §F) defines: DECLINE = browse-only (no erasure); WITHDRAW sets \consent_revoked_at\ → soft-delete + 30-day PII erasure. Spec §K confirms banner is hidden after accept.
'''
    },
]

errors = []
for item in repl_data:
    old_text = item[old]
    new_text = item[new]
    count = content.count(old_text)
    if count == 0:
        errors.append(NOT FOUND:  + item[label])
    elif count > 1:
        errors.append(AMBIGUOUS:  + item[label])
    else:
        content = content.replace(old_text, new_text, 1)
        print(OK:  + item[label])

if errors:
    print()
    print(ERRORS:)
    for e in errors:
        print(  + e)
else:
    if repl_data:
        filepath.write_text(content, encoding=utf-8)
        print()
        print(All replacements applied and file written successfully.)
