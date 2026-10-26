"""Deterministic, explicitly simulated industrial park with typed business roles."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scipy.optimize import least_squares, brentq
from .lmdi import decompose_lmdi
from .config import DATA_DIR, SCENARIOS

VERSION = 'park-v3'
SOURCE = '园区业务重构模拟数据v3（非企业实测）'
# ID, name, short name, role, product/service, process, output unit
CATALOG = [
 ('A','恒岳联合钢铁','恒岳钢铁','steel','钢坯与钢材','高炉转炉联合流程','吨钢'),
 ('B','华新水泥','华新水泥','materials','熟料与水泥','熟料烧成及水泥粉磨','吨水泥'),
 ('C','临港电炉钢','临港电炉','steel','电炉钢','废钢电炉短流程','吨钢'),
 ('D','清源天然气供应','清源燃气','energy','天然气','调压储配','万立方米'),
 ('E','远达轧钢','远达轧钢','steel','轧材','轧制','吨轧材'),
 ('F','中辰矿渣微粉','中辰矿粉','materials','高炉矿渣微粉','烘干粉磨','吨矿粉'),
 ('P01','江海热轧板材','江海热轧','steel','热轧板材','热轧','吨板材'),
 ('P02','海盛冷轧板材','海盛冷轧','steel','冷轧板材','冷轧','吨板材'),
 ('P03','临江特种钢材','临江特钢','steel','特种钢材','特钢加工','吨钢材'),
 ('P04','联兴型钢','联兴型钢','steel','型钢','型钢轧制','吨型钢'),
 ('P05','瑞丰精密钢管','瑞丰钢管','steel','钢管','制管','吨钢管'),
 ('P06','宏远金属制品','宏远金属','steel','金属制品','金属成形','吨制品'),
 ('P07','恒通钢丝制品','恒通钢丝','steel','钢丝','拉丝','吨钢丝'),
 ('P08','滨江精密铸造','滨江铸造','steel','铸件','电炉铸造','吨铸件'),
 ('P09','鑫源锻造','鑫源锻造','steel','锻件','加热锻造','吨锻件'),
 ('P10','东港焦炭供应','东港焦炭','supplier','焦炭','采购仓储','吨供货'),
 ('P11','绿循废钢加工','绿循废钢','supplier','加工废钢','回收分选','吨废钢'),
 ('P12','海联矿石供应','海联矿石','supplier','铁矿石','矿石供应','吨供货'),
 ('P13','华冶合金材料','华冶合金','supplier','铁合金','合金材料供应','吨供货'),
 ('P14','华耐耐火材料','华耐炉材','supplier','耐火材料','耐材制造','吨耐材'),
 ('P15','联益工业气体','联益气体','supplier','氧气与氮气','空气分离','万立方米'),
 ('P16','远虎机械制造','远虎机械','customer','机械装备','机械制造','台装备'),
 ('P17','海川汽车零部件','海川汽配','customer','汽车零部件','零部件制造','万件'),
 ('P18','宏建钢结构','宏建钢构','customer','钢结构','钢结构制造','吨钢构'),
 ('P19','滨海管道装备','滨海管道','customer','管道装备','管道加工','吨装备'),
 ('P20','江湾钢材贸易','江湾钢贸','customer','钢材订单','钢材贸易','吨销售'),
 ('P21','恒创预拌混凝土','恒创混凝土','materials','预拌混凝土','搅拌','立方米'),
 ('P22','瑞成新型墙材','瑞成墙材','materials','墙材','成形养护','万块'),
 ('P23','绿源钢渣资源化','绿源钢渣','materials','钢渣资源化产品','钢渣处理','吨处理量'),
 ('P24','循达再生骨料','循达骨料','materials','再生骨料','破碎分选','吨骨料'),
 ('P25','海筑装配式构件','海筑构件','materials','装配式构件','构件成形','立方米'),
 ('P26','江海园区配电','园区配电','energy','电力','配电运营','MWh供电'),
 ('P27','江海集中供热','园区供热','energy','蒸汽与热力','燃气与余热供热','GJ供热'),
 ('P28','清润工业供水与回用水','清润供水','infra','工业用水与回用水','供水及回用水','立方米供水'),
 ('P29','清澄污水处理','清澄污水','infra','污水接纳处理','集中污水处理','立方米处理量'),
 ('P30','安洁一般固废处置','安洁固废','infra','一般工业固废处置','一般固废处理','吨处置量'),
]
INDUSTRIES = {'steel':'钢铁及金属加工','materials':'建材与资源利用','supplier':'原料及生产配套','customer':'下游制造与贸易','energy':'能源服务','infra':'公共设施服务'}
FACTORS = {'coal':.34,'gas':.202,'electricity':.55,'green_power':.03}

def build_park(data_dir=DATA_DIR):
    rng=np.random.default_rng(20261025)
    profile=json.loads((Path(data_dir)/'reference_case_a.json').read_text(encoding='utf-8'))
    companies=[]; energies=[]; features=[]; operations=[]; service=[]; projects=[]; funds=[]
    periods=[f'2025-{i:02d}' for i in range(1,13)]
    # Match the algorithm document's +2/-9/-5 thousand tonnes through physical inputs.
    shares=np.array([.60,.15,.20,.05]); factors=np.array(list(FACTORS.values()))
    base_energy=100000/(shares@factors)
    def a_records(params):
        growth,energy_ratio,shift=params
        current=shares+np.array([0,0,-shift,shift])
        return pd.DataFrame([dict(period=p,output=50000*q,energy_type=k,energy=base_energy*e*s,emission_factor=f)
          for p,q,e,mix in [('2025-01',1,1,shares),('2025-12',growth,energy_ratio,current)]
          for k,s,f in zip(FACTORS,mix,factors)])
    def residual(params):
        result=decompose_lmdi(a_records(params))
        return np.array([result[k] for k in ('activity','efficiency','energy_structure')])/1000-[2,-9,-5]
    solved=least_squares(residual,[1.022,.93,.03],bounds=([1,.7,0],[1.15,1.1,.15]),xtol=1e-13,ftol=1e-13,gtol=1e-13).x
    a_end=a_records(solved)
    for index,(cid,name,short,role,product,process,unit) in enumerate(CATALOG):
        transition=role in ('steel','materials')
        template='transition' if transition else 'operating'
        node_type=role if role in ('energy','infra') else 'enterprise'
        in_park=cid not in ('P12','P20')
        project={'steel':'加热与电驱系统节能改造','materials':'粉磨及资源利用能效改造'}.get(role,'运行保障与设备更新')
        if cid=='A': project='高炉节能与绿电替代'
        if cid=='C': project='电炉能效与废钢预热改造'
        if cid=='B': project='窑炉余热回收与替代原料改造'
        base_limit=3000 if cid=='A' else int(rng.integers(1000,2800)) if transition else 0
        need=1000 if cid=='A' else int(rng.integers(350,850)) if transition else 0
        company=dict(company_id=cid,company_name=name,short_name=short,industry=INDUSTRIES[role],business_role=role,
          product=product,process_route=process,output_unit=unit,node_type=node_type,in_park=in_park,
          evaluation_model=template,financing_eligible=transition,base_limit=base_limit,project_need=need,
          shock_sensitivity=.3,pd_base=.078,carbon_intensity=0.,target_intensity=0.,project_name=project,
          reference_case=profile['case_id'] if cid=='A' else '',reference_finance_rounding=int(cid=='A'),
          reference_finance_params=json.dumps(profile['finance_params']) if cid=='A' else '{}',data_source=SOURCE,dataset_version=VERSION)
        q0=float(rng.integers(9000,25000)); growth=float(rng.uniform(.96,1.10))
        q0*= {'P16':.015,'P17':.005,'P22':.10,'P25':.30}.get(cid,1.)
        intensity={'B':.85,'C':.65,'E':.45,'F':.12,'P01':.45,'P02':.18,'P03':.55,'P04':.40,'P05':.25,
          'P06':.20,'P07':.22,'P08':.90,'P09':.65,'P10':.003,'P11':.025,'P12':.003,'P13':.02,
          'P14':.70,'P15':4.,'P16':5.,'P17':8.,'P18':.08,'P19':.12,'P20':.003,
          'P21':.015,'P22':.60,'P23':.035,'P24':.012,'P25':.025}.get(cid,.05)
        e0=q0*intensity
        mix=np.array([.45,.25,.25,.05]) if cid in ('A','B') else np.array([0,.18,.72,.10]) if role in ('steel','materials') else np.array([0,.08,.85,.07])
        eratio=float(rng.uniform(.83,.98))*growth
        shift=float(rng.uniform(.02,.07))
        if cid=='A':
            q0=50000; growth,eratio,shift=solved; mix=shares; e0=base_energy
        for month,period in enumerate(periods):
            t=month/11; season=1+.018*np.sin(month/11*2*np.pi)
            output=q0*(1+(growth-1)*t)*season
            m=mix+np.array([0,0,-shift*t,shift*t])
            energy=e0*(1+(eratio-1)*t)*season
            for fuel,fraction in zip(FACTORS,m):
                if fraction>0:
                    energies.append(dict(company_id=cid,period=period,output=output,output_unit=unit,energy_type=fuel,
                      energy=energy*fraction,energy_unit='MWh等价值',emission_factor=FACTORS[fuel],factor_unit='tCO2/MWh等价值',data_source=SOURCE))
            if not transition:
                capacity=q0*1.3
                service.append(dict(company_id=cid,period=period,service=product,quantity=output,capacity=capacity,
                  unit=unit,availability=.975+(index%4)*.005,backup_hours=8+(index%5)*8,data_source=SOURCE))
        frame=pd.DataFrame([r for r in energies if r['company_id']==cid])
        lmdi=decompose_lmdi(frame.loc[frame.period.isin([periods[0],periods[-1]])])
        negative=sum(-lmdi[k] for k in ('activity','efficiency','energy_structure') if lmdi[k]<0)
        trend=1-(lmdi['current_emissions']/(q0*growth))/(lmdi['base_emissions']/q0)
        feature=dict(company_id=cid,company_name=name,lmdi_efficiency_share=max(0,-lmdi['efficiency'])/negative if negative else 0,
          lmdi_energy_share=max(0,-lmdi['energy_structure'])/negative if negative else 0,intensity_trend=trend,
          project_progress=float(rng.uniform(.60,.93)),milestone_delay_days=float(rng.integers(0,25)),fund_usage_match=float(rng.uniform(.85,.99)),
          own_fund_arrival=float(rng.uniform(.72,.97)),cashflow_coverage=float(rng.uniform(1.1,2.)),
          energy_cost_ratio=float(rng.uniform(.18,.34)),data_completeness=.96,evaluation_model=template,
          shock_sensitivity=.3,direct_shock_sensitivity=0.)
        if cid=='A':
            # Reconstructed LMDI facts remain derived; only non-energy case inputs are calibrated.
            feature.update({k:v for k,v in profile['features'].items() if k in feature and k not in ('company_name','lmdi_efficiency_share','lmdi_energy_share','intensity_trend')})
        feature.update(gas_sensitivity=float(mix[1]*1.6),electricity_sensitivity=float((mix[2]+mix[3])*.6),
          coal_sensitivity=float(mix[0]*.8),carbon_sensitivity=min(1.,float(lmdi['base_emissions']/q0)*.15),demand_sensitivity=.25 if transition else .1)
        if cid=='A': feature['gas_sensitivity']=profile['features']['shock_sensitivity']
        company['carbon_intensity']=lmdi['current_emissions']/(q0*growth)
        company['target_intensity']=company['carbon_intensity']*.88
        companies.append(company); features.append(feature)
        # Operational inputs are separate from transition-target probabilities.
        operations.append(dict(company_id=cid,baseline_risk=.07+(index%6)*.012,gas_sensitivity=.18 if cid=='P27' else .025 if cid=='D' else 0 if cid in ('P26','P28','P29','P30') else .03,
          electricity_sensitivity=.23 if cid in ('P15','P28','P29') else .07,coal_sensitivity=.02,carbon_sensitivity=.03,
          demand_sensitivity=.45 if role=='customer' else .10,risk_horizon='未来12个月履约与运行风险指数',data_source=SOURCE))
        projects.append(dict(company_id=cid,project_name=project,project_need=need,project_progress=feature['project_progress'],milestone_delay_days=feature['milestone_delay_days'],planned_completion='2026-12',expected_reduction_tco2=0 if not transition else max(0,-lmdi['total_change'])))
        funds.append(dict(company_id=cid,fund_usage_match=feature['fund_usage_match'],own_fund_arrival=feature['own_fund_arrival'],payment_verified=False,supplier_type='项目设备与施工服务',data_source=SOURCE))
    edges=[]
    def link(source,target,kind,item,share,critical=.8,days=14,mechanism=''):
        # Stored direction: risk source -> dependent, never shipment direction inferred from name.
        edges.append(dict(relation_id=f'park-{len(edges)+1:03d}',source=source,target=target,relation_type=kind,
          dependency_class={'采购依赖':'supply','销售依赖':'supply','能源依赖':'energy','公共设施依赖':'infra'}[kind],
          commodity=item,share=share,share_basis=f'{target}的{item}{"销售收入" if kind=="销售依赖" else "需求"}总量',criticality=critical,
          weight=share*critical,replacement_days=days,inventory_days=max(0,days//2),reporting_period='2025-12',
          direction_basis=f'{source}的{item}{"订单与回款" if kind=="销售依赖" else "供给或服务"}变化影响{target}',data_source=SOURCE,evidence_status='模拟业务·未核验'))
    # Material chains: supplier -> buyer. Demand chains have customer -> seller.
    for s,t,item,share in [('P10','A','焦炭',.55),('P12','A','铁矿石',.48),('P13','A','合金材料',.25),('P14','A','耐火材料',.30),('P15','A','氧氮气',.70),
      ('P11','C','加工废钢',.65),('P13','C','合金材料',.40),('P15','C','氧氮气',.60),('A','E','钢坯',.50),('A','P01','钢坯',.40),
      ('P01','P02','热轧卷',.60),('C','P03','特种钢坯',.45),('E','P04','型钢坯料',.40),('P02','P05','冷轧带钢',.50),
      ('E','P06','钢材',.35),('P04','P07','盘条',.45),('P11','P08','加工废钢',.40),('P03','P09','锻造钢坯',.40),
      ('A','F','粒化高炉矿渣',.70),('A','P23','钢渣资源化原料',.65),('F','B','矿渣微粉',.35),('B','P21','水泥',.50),
      ('P24','P21','再生骨料',.30),('P23','P22','合规钢渣骨料',.25),('B','P22','水泥',.40),('P21','P25','混凝土',.45),('P04','P25','钢材',.35),
      ('E','P16','钢材',.40),('P02','P17','冷轧板材',.50),('P04','P18','型钢',.60),('P05','P19','钢管',.55),('P01','P20','热轧板材',.35)]: link(s,t,'采购依赖',item,share)
    for customer,seller,item,share in [('E','A','钢坯',.18),('P16','E','轧材',.30),('P18','P04','型钢',.35),('P17','P02','冷轧板材',.32),('P19','P05','钢管',.42),('P20','P01','热轧板材',.28),('B','F','矿渣微粉',.30)]: link(customer,seller,'销售依赖',item,share,.8,30)
    manufacturing=[r[0] for r in CATALOG if r[3] in ('steel','materials')]
    # Explicitly typed utilities with capacity sized from aggregate metered demand.
    for cid in manufacturing:
        link('P26',cid,'能源依赖','电力',.70,.85,1)
    for cid in ['A','E','P01','P03','P09','F','B']:
        link('D',cid,'能源依赖','天然气',.65,.70,3)
    for cid in ['F','P22','P25']:
        link('P27',cid,'能源依赖','蒸汽',.55,.65,3)
    for cid in ['A','B','C','E','P01','P02','P08','P21','P25']:
        link('P28',cid,'公共设施依赖','工业用水',.65,.65,1)
        link('P29',cid,'公共设施依赖','污水处理',.70,.65,2)
    for cid in ['A','B','C','P08','P23','P24']:
        link('P30',cid,'公共设施依赖','一般工业固废处置',.40,.45,7)
    for cid in ['D','P27','P28','P29','P30','P15']:
        link('P26',cid,'能源依赖','电力',.75,.70,1)
    link('D','P27','能源依赖','天然气',.60,.65,3)
    link('P29','P28','公共设施依赖','回用水原水',.35,.50,2)
    link('A','P27','能源依赖','回收余热',.20,.50,5)
    # Named, bounded protections; coefficients calibrated only after all topology is fixed.
    protection=[]
    for edge in edges:
        if edge['target']=='A' or (edge['source']=='P26' and edge['target'] in ('D','P28','P29','P15')):
            mechanism={'energy':'备用能源与切换保障','infra':'应急容量与停运缓冲','supply':'备选供应或订单分散'}[edge['dependency_class']]
            protection.append(dict(source=edge['source'],target=edge['target'],relation_type=edge['relation_type'],coverage_ratio=.18,
              effectiveness=.85,availability=.95,stress_sensitivity=.6,stress_reference_change=.30,stress_driver='天然气价格',
              mechanism=mechanism+'及园区应急采购周转额度；燃气成本占用应急预算（模拟）',data_source=SOURCE,reporting_period='2025-12',evidence_status='模拟参数·未核验'))
    # One canonical monthly flow per provider/customer/commodity; sales dependencies
    # reference the same flow as purchases, with reversed risk endpoints.
    energy_frame=pd.DataFrame(energies)
    flows={}
    for edge in edges:
        seller,buyer=(edge['target'],edge['source']) if edge['relation_type']=='销售依赖' else (edge['source'],edge['target'])
        item=edge['commodity']; total=0
        unit={'电力':'MWh','天然气':'万立方米','氧氮气':'万立方米','蒸汽':'GJ','回收余热':'GJ','工业用水':'立方米','污水处理':'立方米','回用水原水':'立方米'}.get(item,'吨')
        for period in periods:
            key=(seller,buyer,item,period)
            if key not in flows:
                target_energy=energy_frame.loc[(energy_frame.company_id==buyer) & (energy_frame.period==period)]
                if item=='电力': demand=target_energy.loc[target_energy.energy_type.isin(['electricity','green_power']),'energy'].sum()
                elif item=='天然气': demand=target_energy.loc[target_energy.energy_type=='gas','energy'].sum()/100
                elif item in ('蒸汽','回收余热'): demand=target_energy.energy.sum()*.12*3.6
                else: demand=float(target_energy.output.max())*{'焦炭':.40,'铁矿石':1.6,'工业用水':2,'污水处理':1.4,'一般工业固废处置':.1,'回用水原水':.4,'氧氮气':.006}.get(item,1.04 if item in ('钢坯','热轧卷','特种钢坯','型钢坯料','冷轧带钢','盘条','锻造钢坯') else .25)
                quantity=float(demand*edge['share'])
                flows[key]=dict(flow_id=f'flow-{len(flows)+1:04d}',provider_id=seller,customer_id=buyer,commodity=item,period=period,
                                quantity=quantity,unit=unit,data_source=SOURCE)
            total+=flows[key]['quantity']
        edge['annualized_quantity']=total
        edge['quantity_unit']=unit
    water_balance=[]
    for period in periods:
        supplied=sum(flow['quantity'] for flow in flows.values() if flow['provider_id']=='P28' and flow['period']==period)
        treated=sum(flow['quantity'] for flow in flows.values() if flow['provider_id']=='P29' and flow['commodity']=='污水处理' and flow['period']==period)
        recycled=supplied*.20*.35
        flows[('P29','P28','回用水原水',period)]['quantity']=recycled
        water_balance.append(dict(period=period,water_supplied=supplied,fresh_water=supplied-recycled,reclaimed_water=recycled,
          wastewater_received=treated,treated_water_discharged=treated-recycled,unit='立方米',data_source=SOURCE))
    for edge in edges:
        seller,buyer=(edge['target'],edge['source']) if edge['relation_type']=='销售依赖' else (edge['source'],edge['target'])
        edge['annualized_quantity']=sum(flows[(seller,buyer,edge['commodity'],period)]['quantity'] for period in periods)
    # Reconcile service ledgers to actual allocated monthly flows and leave 25% reserve.
    for cid in [row[0] for row in CATALOG if row[3] in ('energy','infra','supplier')]:
        quantities={period:sum(row['quantity'] for row in flows.values() if row['provider_id']==cid and row['period']==period and (cid!='P29' or row['commodity']=='污水处理')) for period in periods}
        capacity=max(quantities.values())*1.25
        for row in service:
            if row['company_id']==cid:
                row['quantity']=quantities[row['period']]
                row['capacity']=capacity
                row['allocated_customer_quantity']=row['quantity']
                row['unallocated_reserve']=row['capacity']-row['quantity']
                if cid=='P29': row['reclaimed_water_output']=sum(flow['quantity'] for flow in flows.values() if flow['provider_id']==cid and flow['period']==row['period'] and flow['commodity']=='回用水原水')
                matching=next((flow for flow in flows.values() if flow['provider_id']==cid),None)
                if matching: row['unit']=matching['unit']
    # Utility and supplier own-use energy follows metered service throughput,
    # rather than applying a steel-like intensity to cubic metres of water.
    utility_rates={'D':.4,'P26':.02,'P27':1/(3.6*.90),'P28':.0005,'P29':.0006,'P30':.020,
                   'P10':.003,'P11':.025,'P12':.003,'P13':.02,'P14':.70,'P15':4.}
    for row in service:
        cid=row['company_id']
        if cid not in utility_rates: continue
        mask=energy_frame.company_id.eq(cid)&energy_frame.period.eq(row['period'])
        total=row['quantity']*utility_rates[cid]
        share=pd.Series({'gas':.92,'electricity':.08}) if cid=='P27' else pd.Series({'electricity':.90,'green_power':.10})
        # Retain a consistent set of energy channels for enterprise data interfaces.
        present=energy_frame.loc[mask,'energy_type']
        mix=present.map(share).fillna(0).to_numpy()
        if not mix.sum(): mix=np.ones(len(present))
        mix=np.maximum(mix,1e-9);mix/=mix.sum()
        energy_frame.loc[mask,'output']=row['quantity']
        energy_frame.loc[mask,'energy']=total*mix
        energy_frame.loc[mask,'output_unit']=row['unit']
    # Reflect the canonical transaction's actual share of the seller's output.
    for edge in edges:
        if edge['relation_type']=='销售依赖':
            output=energy_frame.loc[energy_frame.company_id.eq(edge['target'])].groupby('period').output.max().sum()
            edge['share']=min(1.,edge['annualized_quantity']/output)
            edge['weight']=edge['share']*edge['criticality']
    project_history=[]; payments=[]; operating_history=[]
    for company,feature in zip(companies,features):
        cid=company['company_id']
        for month,period in enumerate(periods):
            frame=energy_frame.loc[(energy_frame.company_id==cid)&(energy_frame.period==period)]
            # Prices and cash flows are simulated ledger inputs, with an explicit common energy unit.
            bill=sum(row.energy*{'coal':220,'gas':360,'electricity':580,'green_power':620}[row.energy_type] for row in frame.itertuples())
            operating_cost=bill/max(feature['energy_cost_ratio'],.01)
            debt_service=operating_cost*.08
            operating_history.append(dict(company_id=cid,period=period,energy_expense=bill,operating_cost=operating_cost,
              operating_cashflow=debt_service*feature['cashflow_coverage'],debt_service=debt_service,currency='元',data_source=SOURCE))
            if company['evaluation_model']!='transition': continue
            progress=feature['project_progress']*(month+1)/12
            own_plan=company['project_need']*.30
            own_received=own_plan*feature['own_fund_arrival']*(month+1)/12
            project_history.append(dict(company_id=cid,period=period,project_name=company['project_name'],
              actual_progress=progress,planned_progress=min(1,progress+feature['milestone_delay_days']/365),
              milestone_delay_days=feature['milestone_delay_days'],actual_investment=company['project_need']*progress,
              own_fund_plan=own_plan,own_fund_received=own_received,amount_unit='万元',data_source=SOURCE))
            loan_payment=(company['project_need']*feature['project_progress']-own_plan*feature['own_fund_arrival'])/12
            for matched,ratio in [(True,feature['fund_usage_match']),(False,1-feature['fund_usage_match'])]:
                payments.append(dict(payment_id=f'pay-{len(payments)+1:04d}',company_id=cid,period=period,
                  amount=loan_payment*ratio,amount_unit='万元',purpose='项目设备与施工' if matched else '待补充用途对应关系',
                  rule_matched=matched,bank_verified=False,data_source=SOURCE))
    return dict(companies=pd.DataFrame(companies),features=pd.DataFrame(features),energy=energy_frame,network=pd.DataFrame(edges),
      network_mitigation=pd.DataFrame(protection),operation_profiles=pd.DataFrame(operations),service_history=pd.DataFrame(service),
      business_flows=pd.DataFrame(flows.values()),water_balance=pd.DataFrame(water_balance),project_history=pd.DataFrame(project_history),fund_payments=pd.DataFrame(payments),
      operating_history=pd.DataFrame(operating_history),projects=pd.DataFrame(projects),funds=pd.DataFrame(funds))

EXTRA_FILES={key:f'{key}.csv' for key in ('operation_profiles','service_history','business_flows','project_history','fund_payments','operating_history','water_balance')}

def calibrate_case(data, profile):
    """Bounded calibration of explicit inputs, never assignment to predicted outputs."""
    from .pipeline import CarbonFinancePipeline
    pipeline=CarbonFinancePipeline(data)
    mask=data['features'].company_id.eq('A')
    def quality(completeness):
        data['features'].loc[mask,'data_completeness']=completeness
        row=pipeline.evaluate_entities().set_index('company_id').loc['A']
        return row.data_quality-profile['reference_outputs']['normal_quality']
    brentq(quality,.95,.99,xtol=1e-12)
    def gas_probability(sensitivity):
        data['features'].loc[mask,'gas_sensitivity']=sensitivity
        row=pipeline.evaluate_entities(SCENARIOS['天然气价格上涨30%']).set_index('company_id').loc['A']
        return row.p_target-profile['reference_outputs']['gas_probability']
    brentq(gas_probability,0,.8,xtol=1e-12)
    protection=data['network_mitigation']; incoming=protection.target.eq('A')
    def residual(params):
        protection.loc[incoming,'coverage_ratio']=params[0]
        protection.loc[incoming,'stress_sensitivity']=params[1]
        return [pipeline.run(s)['companies'].set_index('company_id').loc['A','network_risk']-target
                for s,target in [('正常情景',.16),('天然气价格上涨30%',.31)]]
    solved=least_squares(residual,[.17,.8],bounds=([0,0],[1,1]),diff_step=.001,xtol=1e-12,gtol=1e-12,ftol=1e-12)
    if max(abs(solved.fun))>1e-8: raise ValueError('既定业务约束无法拟合策划书A，请复核模拟机制')
    residual(solved.x)
    # Keep the filed accounting ledger aligned with calibrated cash/quality facts.
    own=data['operating_history'].company_id.eq('A')
    data['operating_history'].loc[own,'operating_cashflow']=data['operating_history'].loc[own,'debt_service']*data['features'].loc[mask,'cashflow_coverage'].iloc[0]
    feature=data['features'].loc[mask].iloc[0].to_dict()
    updated=json.loads(json.dumps(profile))
    updated['features']=feature
    updated['incoming_protection']={k:float(protection.loc[incoming,k].iloc[0]) for k in ('coverage_ratio','effectiveness','availability','stress_sensitivity','stress_reference_change')}
    updated['incoming_protection']['stress_driver']='天然气价格'
    updated['calibration_note']='park-v2：LMDI特征从能源记录派生；以模拟应急预算保障参数拟合A正常及燃气成本压力，不覆盖模型或风险输出。'
    return updated

def write_park(data,directory):
    from .data import FILES
    directory=Path(directory); directory.mkdir(parents=True,exist_ok=True)
    files={**FILES,**EXTRA_FILES,'network_mitigation':'network_mitigation.csv'}
    for key,frame in data.items():
        if key in files: frame.to_csv(directory/files[key],index=False,encoding='utf-8-sig',float_format='%.15g')
