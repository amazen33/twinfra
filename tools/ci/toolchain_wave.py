"""ADR-0049 Amendment 1: conservative proposals, never automatic admission. MIT."""
from datetime import date, timedelta

CRITICAL={'GO-2026-6612','CVE-2026-78663','GO-2026-6604','CVE-2026-56857'}
CORE_MODULES={'stdlib','golang.org/x/net','golang.org/x/crypto','golang.org/x/text','golang.org/x/sys'}
HIGH_FIXES={'golang.org/x/crypto':'0.56.0','golang.org/x/net':'0.60.0','golang.org/x/text':'0.41.0'}


def listed(finding):
    ids=set(finding.get('aliases',[]))|{finding['vulnerability']}
    if finding['severity']=='Critical':
        return finding['package'] in CORE_MODULES and bool(ids&CRITICAL)
    expected=HIGH_FIXES.get(finding['package'])
    return finding['severity']=='High' and bool(expected) and expected in [v.lstrip('v') for v in finding.get('fixVersions',[])]


def review(findings, *, eligible_fixed_release, controls, on=None):
    """Return explicit blockers or owner-review proposals with unchanged gate semantics.

    stdlib-only Highs are NOT named by the amendment. They cannot be smuggled
    into the x/net/crypto/text list because they share a language toolchain.
    WO-09 further limits both severities to 30 days.
    """
    on=on or date.today();blocking=[v for v in findings if v.get('blocked',bool(v.get('blockReason')))]
    reasons=[]
    if eligible_fixed_release:reasons.append('An eligible upstream release contains the fixes')
    if not controls.get('clusterOrLanOnly') or not controls.get('externalEgress') or not controls.get('noExternalService'):
        reasons.append('Missing component isolation controls')
    if any(v.get('kev') for v in findings):reasons.append('KEV cannot use the toolchain-wave rule')
    unlisted=[dict(package=v['package'],vulnerability=v['vulnerability'],severity=v['severity']) for v in blocking if not listed(v)]
    if unlisted:reasons.append('Blocking findings outside the owner-named toolchain wave')
    entries=[]
    if blocking and not reasons:
        for value in blocking:
            entry={k:value[k] for k in ('target','package','version','vulnerability','severity')}
            entry.update(owner='amazen33',approvedBy='pending-owner',createdOn=on.isoformat(),
                         expires=(on+timedelta(days=30)).isoformat(),workOrder='WO-34',
                         reason='ADR-0049 Amendment 1 / WO-09: '+value['vulnerability']+
                         '; fixes '+', '.join(value.get('fixVersions',[]))+
                         '; cluster-internal only; external egress only to '+controls['externalEgress']+
                         '; no Service exposed outside the namespace. No eligible fixed upstream release; '+
                         'not KEV. Owner batch approval required in this component PR. Refresh within 14 days '+
                         'of an eligible fixed upstream release; immediate expedite if KEV.')
            entries.append(entry)
    return {'status':'blocked' if reasons else 'owner-review-required' if entries else 'no-exception-needed',
            'blockers':reasons,'unlisted':unlisted,'proposedExceptions':entries}
