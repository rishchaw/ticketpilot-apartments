"""Small reproducible smoke evaluation; NOT a realistic business accuracy claim.
Run python -m ticketpilot.evaluate_pipeline (no external API or database).
"""
from __future__ import annotations
import json
import statistics
import time
from ticketpilot.api import TicketInput, _analyze

CASES = [
    ('access', 'KB-001', 'Forgot my password', 'I am locked out after several failed login attempts.'),
    ('access', 'KB-002', 'Cannot use two-factor verification', 'My MFA authentication code does not work.'),
    ('access', 'KB-003', 'SSO access', 'I receive 403 forbidden after SAML single sign on.'),
    ('billing', 'KB-004', 'Invoice charged twice', 'I received a duplicate charge and incorrect billing invoice.'),
    ('billing', 'KB-005', 'Payment declined', 'My payment failed at checkout even though my card works.'),
    ('billing', 'KB-006', 'Refund renewal', 'Can I get a refund for a cancelled subscription?'),
    ('infrastructure', 'KB-007', 'Production API down', 'The production service is unreachable and returns 503 server errors.'),
    ('infrastructure', 'KB-008', 'Slow API responses', 'Our server is timing out and queries have high database latency.'),
    ('infrastructure', 'KB-009', 'Security breach alert', 'Potential security breach and sensitive data leak.'),
    ('product', 'KB-010', 'Mobile UI broken', 'The dashboard has a broken layout and hidden button on my browser.'),
    ('product', 'KB-011', 'CSV report export', 'Clicking export fails to download the CSV report.'),
    ('product', 'KB-012', 'Feature request', 'Please add a scheduling feature to the product analytics dashboard.'),
]

def main():
    results=[]; durations=[]
    for expected_category, expected_article, title, body in CASES:
        start=time.perf_counter()
        result=_analyze(TicketInput(title=title,text=body))
        durations.append((time.perf_counter()-start)*1000)
        results.append({'expected_category':expected_category,'predicted_category':result['predicted_category'],
                        'expected_kb':expected_article,'retrieved': [s['id'] for s in result['sources']],
                        'category_correct':result['predicted_category']==expected_category,
                        'kb_top3_hit':expected_article in [s['id'] for s in result['sources']]})
    summary={
        'evaluation':'12 authored synthetic smoke scenarios; not independently validated real-world data',
        'count':len(results),
        'classification_accuracy':round(sum(r['category_correct'] for r in results)/len(results),3),
        'kb_retrieval_hit_at_3':round(sum(r['kb_top3_hit'] for r in results)/len(results),3),
        'median_latency_ms_warm_or_cold_mixed':round(statistics.median(durations),2),
        'individual_cases':results,
    }
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
