"""Explain one scenario run; never feed propagated risks back as new shocks."""
from carbon_finance.config import DEMO_PARAMS
from carbon_finance.network import path_components


def explain_network(company_id, network, baseline, prepared, baseline_prepared=None):
    ids = network.company_id.tolist()
    position = {key: index for index, key in enumerate(ids)}
    names = network.set_index('company_id').company_name.to_dict()
    current = network.set_index('company_id').loc[ids]
    normal = baseline.set_index('company_id').loc[ids]
    matrix, decay = prepared['matrix'], DEMO_PARAMS['propagation_decay']
    baseline_prepared = baseline_prepared or prepared
    own, base_own = current.own_risk.to_numpy(), normal.own_risk.to_numpy()
    channels = {}
    for row in prepared['relations'].itertuples():
        if row.effective_weight > 0:
            channels.setdefault((row.source, row.target), []).append(row.relation_id)

    def path(keys):
        indices = [position[key] for key in keys]
        selected = path_components(indices, prepared, own, decay)
        normal_value = path_components(indices, baseline_prepared, base_own, decay)
        value, base = selected['contribution'], normal_value['contribution']
        return {'path': ' → '.join(names[key] for key in keys), 'node_ids': keys,
                'order': len(keys)-1, 'contribution': value, 'baseline_contribution': base,
                'delta': value-base,
                **selected,
                'baseline_gross_contribution': normal_value['gross_contribution'],
                'baseline_mitigation_contribution': normal_value['mitigation_contribution'],
                'relation_ids': [relation for pair in zip(keys, keys[1:]) for relation in channels[pair]]}

    incoming, outgoing = [], []
    origin = position[company_id]
    for other in ids:
        index = position[other]
        if matrix[origin, index] > 0:
            incoming.append(path([other, company_id]))
        if matrix[index, origin] > 0 and other != company_id:
            outgoing.append(path([company_id, other]))
        for middle in ids:
            mid = position[middle]
            if matrix[origin, mid] > 0 and matrix[mid, index] > 0:
                incoming.append(path([other, middle, company_id]))
            if other != company_id and matrix[index, mid] > 0 and matrix[mid, origin] > 0:
                outgoing.append(path([company_id, middle, other]))
    incoming.sort(key=lambda item: (-abs(item['contribution']), item['path']))
    outgoing.sort(key=lambda item: (-abs(item['contribution']), item['path']))
    recipients = []
    for target in ids:
        paths = [item for item in outgoing if item['node_ids'][-1] == target]
        if not paths:
            continue
        value = sum(item['contribution'] for item in paths)
        base = sum(item['baseline_contribution'] for item in paths)
        recipients.append({'company_id': target, 'company_name': names[target],
                           'contribution': value, 'baseline_contribution': base, 'delta': value-base,
                           'gross_contribution': sum(p['gross_contribution'] for p in paths),
                           'mitigation_contribution': sum(p['mitigation_contribution'] for p in paths),
                           'first_order_contribution': sum(p['contribution'] for p in paths if p['order'] == 1),
                           'second_order_contribution': sum(p['contribution'] for p in paths if p['order'] == 2),
                           'risk': float(current.loc[target, 'network_risk']),
                           'baseline_risk': float(normal.loc[target, 'network_risk']),
                           'risk_delta': float(current.loc[target, 'network_risk']-normal.loc[target, 'network_risk']),
                           'paths': paths})
    recipients.sort(key=lambda item: (-abs(item['contribution']), item['company_id']))
    return {'incoming_paths': incoming, 'outgoing_paths': outgoing, 'recipients': recipients,
            'contribution_basis': 'pre_clip', 'max_order': 2,
            'decay': decay, 'baseline_scenario': '正常情景',
            'effect_method': 'gross_risk_minus_explicit_mitigation'}
