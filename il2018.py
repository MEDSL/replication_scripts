import os

import pandas as pd
import electioncleaner as EC
import numpy as np
DataFrame = pd.core.frame.DataFrame
Series = pd.core.series.Series


def load_file(file: str) -> DataFrame:
    data = pd.read_csv(file)
    data = data[['JurisName', 'CandidateName', 'ContestName', 'PrecinctName', 'Registration',
                 'PartyName', 'VoteCount']]
    data.columns = ['County', 'Candidate', 'Office', 'Precinct', 'Registered Voters', 'Party',
                    'Votes']
    data['Office'] = data['Office'].fillna('BALLOTS CAST')
    data['Candidate'] = data['Candidate'].fillna('TOTAL')
    registration = (data[~data['Candidate'].isin({'Over Votes', 'Under Votes'})]
                    [['County', 'Precinct', 'Registered Voters']].drop_duplicates())
    registration.columns = ['County', 'Precinct', 'Votes']
    registration['Candidate'] = 'TOTAL'
    registration['Office'] = 'REGISTERED VOTERS'
    registration['Party'] = ''
    data = data.drop('Registered Voters', axis=1)
    data = data.append(registration).sort_values(['Office', 'Precinct', 'Party', 'Candidate'])
    data = data.reset_index(drop=True)
    return data


def load_all_data(prepare_pickle=True) -> DataFrame:
    if prepare_pickle:
        data = pd.DataFrame()

        for (_, _, files) in os.walk(os.getcwd()+'/raw'):
            for file in files:
                if '~' in file:
                    continue
                print(f'*Reading file raw/{file}...')
                file_data = load_file(f'raw/{file}')
                data = data.append(file_data)
                print(f'Read file raw/{file}...')
        # Some cities within counties report results separately. We fix that now by merging
        # with the parent county
        data['preserve_juris'] = data['County']
        data['County'] = data['County'].replace({
            '.*BLOOMINGTON': 'McLEAN',
            '.*CHICAGO': 'COOK',
            '.*DANVILLE': 'VERMILION',
            '.*EAST ST. LOUIS': 'ST. CLAIR',
            '.*GALESBURG': 'KNOX',
            '.*ROCKFORD': 'WINNEBAGO',
            }, regex=True)
        # Drop county aggregates

        ### testing retaining blank precincts, which are leading to down ballot candidate undercounts
        # data = data[~data['Precinct'].isna()]
        data['Precinct'] = data['Precinct'].fillna("COUNTY FLOATING")

        data = data.sort_values(['County','preserve_juris', 'Office', 'Precinct', 'Party', 'Candidate'])
        data = data.reset_index(drop=True)
        data.to_pickle('raw_IL18.pkl')

    data = pd.read_pickle('raw_IL18.pkl')
    return data


def make_state(data: DataFrame) -> DataFrame:
    print('*Parsing IL18 `state`...')
    # State is Illinois by definition
    data = EC.state.add_state_codes(data, state='Illinois')

    print('Parsed IL18 `state`.')
    return data


def make_precinct(data: DataFrame) -> DataFrame:
    print('*Parsing IL18 `precinct`...')
    # Data is pulled straight from `Precinct`.
    data['precinct'] = data['Precinct'].astype(str).str.strip().str.upper()
    data['precinct'] = data['precinct'].str.replace('\.0','',regex=True)
    print('Parsed IL18 `precinct`.')
    return data


def make_office(data: DataFrame) -> DataFrame:
    print('*Parsing IL18 `office`...')

    # Data is pulled from `Office`
    data['temp_office'] = data['Office'].str.upper()

    # First, remove any extraneous whitespace/characters
    data['temp_office'] = data['temp_office'].str.strip().replace({
        r' ( )+': ' ',
        r' -': '-',
        r'\.': '',
        r'/ ': '/',
        r'&': 'AND',
        }, regex=True)

    data = EC.fix_ordinals(data, 'temp_office', '|'.join([
        'APPELLATE',
        'CONGRESS',
        'CIRCUIT',
        'REPRESENTATIVE',
        'SENATE',
        'SUPREME',
        ]))

    # Do this separately as some subcircuits also include circuit
    data = EC.fix_ordinals(data, 'temp_office', 'SUBCIRCUIT')

    # Standardize names
    standard_names = {
        r'PRESIDENT.*': 'US PRESIDENT',
        r'UNITED STATES SENATOR.*': 'US SENATE',
        r'CONGRESS': 'US HOUSE:',
        r'SENATE': 'STATE SENATE:',
        r'REPRESENTATIVE': 'STATE HOUSE:',
        r'NEVILLE, JR': 'NEVILLE JR',  # Remove comma,
        r'PRAIRIE DUPONT LEVEE AND SANITARY DISTRICT':
            'TRUSTEES OF THE PRAIRIE DUPONT LEVEE AND SANITARY DISTRICT',  # Match reporting source
        r'GOVERNOR AND LIEUTENANT GOVERNOR':'GOVERNOR'}

    data['temp_office'] = data['temp_office'].replace(standard_names, regex=True)

    # We will remove district mark and fix retentions/vacancies later
    print('Partially parsed IL18 `office` (1/3).')
    return data


def make_party_detailed(data: DataFrame) -> DataFrame:
    print('*Parsing IL18 `party_detailed...`')

    # Data is pulled from `Party`
    data['party_detailed'] = data['Party'].fillna('').str.upper()

    # Standardize
    data['party_detailed'] = data['party_detailed'].replace({
        'DEMOCRATIC': 'DEMOCRAT',
        'DEMOCRACT': 'DEMOCRAT',
        'NON-PARTISAN': 'NONPARTISAN',
        'AMERICAN SOLIDARITY PARTY': 'AMERICAN SOLIDARITY',
        '.*SOCIALISM.*': 'PARTY FOR SOCIALISM AND LIBERATION',
        'WILLIE WILSON.*': 'WILLIE WILSON',
        'PRO-GUN PRO-LIFE.*': 'PRO-GUN PRO-LIFE',
        'LIBERTARIAN.*': 'LIBERTARIAN',
        'LINCOLN HERITAGE PARTY': 'LINCOLN HERITAGE'
        }, regex=True)

    # A few candidates did not list party for some records (Lake County)
    # so we manually add them based on the rest of the data
    # missing_party = {
        # 'IAN PEAK': 'LIBERTARIAN',
        # 'JOHN COOK': 'INDEPENDENT',
        # 'RALPH SIDES': 'PRO-GUN PRO-LIFE',
        # 'BRIAN CARROLL': 'AMERICAN SOLIDARITY',
        # 'DONALD J. TRUMP': 'REPUBLICAN',
        # 'GLORIA LA RIVA': 'PARTY FOR SOCIALISM AND LIBERATION',
        # 'HOWIE HAWKINS': 'GREEN',
        # 'JO JORGENSEN': 'LIBERTARIAN',
        # 'JOSEPH R. BIDEN': 'DEMOCRAT',
        # 'DANNY MALOUF': 'LIBERTARIAN',
        # 'DAVID F. BLACK': 'GREEN',
        # 'MARK C. CURRAN JR.': 'REPUBLICAN',
        # 'RICHARD J. DURBIN': 'DEMOCRAT',
        # 'WILLIE L. WILSON': 'WILLIE WILSON',

        # 'BRAD SCHNEIDER': 'DEMOCRAT',
        # 'VALERIE RAMIREZ MUKHERJEE': 'REPUBLICAN',
        # 'JIM OBERWEIS': 'REPUBLICAN',
        # 'LAUREN UNDERWOOD': 'DEMOCRAT',
        # 'BILL REDPATH': 'LIBERTARIAN',
        # 'JEANNE IVES': 'REPUBLICAN',
        # 'SEAN CASTEN': 'DEMOCRAT',
        # 'CHRISTOPHER KASPERSKI': 'REPUBLICAN',
        # 'MELINDA BUSH': 'DEMOCRAT',
        # 'CHRIS BOS': 'REPUBLICAN',
        # 'MARY EDLY-ALLEN': 'DEMOCRAT',
        # 'ALIA SARFRAZ': 'GREEN',
        # 'MARCI SUELZER': 'DEMOCRAT',
        # 'MARTIN MCLAUGHLIN': 'REPUBLICAN',
        # 'JONATHAN CARROLL': 'DEMOCRAT',
        # 'BOB MORGAN': 'DEMOCRAT',
        # 'DANIEL DIDECH': 'DEMOCRAT',
        # 'RITA MAYFIELD': 'DEMOCRAT',
        # 'DAN YOST': 'REPUBLICAN',
        # 'JOYCE MASON': 'DEMOCRAT',
        # 'JIM WALSH': 'REPUBLICAN',
        # 'SAM YINGLING': 'DEMOCRAT',
        # 'LESLIE ARMSTRONG-MCLEOD': 'DEMOCRAT',
        # 'TOM WEBER': 'REPUBLICAN',
        # 'BOB MORGAN': 'DEMOCRAT',
        # }
    # data['party_detailed'] = data['party_detailed'].mask(
    #     data['Candidate'].str.upper().isin(missing_party.keys()),
    #     data['Candidate'].str.upper().replace(missing_party, regex=True)
    # )
    # The following candidates are writeins, so should have empty party
    writeins = {
        'WRITE-IN',
        'WRITEIN',
        # 'FRANK ROWDER',
        # 'JON HARLSON',
        # 'JOSEPH MONACK',
        # 'GENERAL PARKER',
        }
    data['party_detailed'] = data['party_detailed'].mask(
        data['Candidate'].str.upper().isin(writeins), "")

    print('Parsed IL18 `party_detailed`.')
    return data


def make_party_simplified(data: DataFrame) -> DataFrame:
    print('*Parsing IL18 `party_simplified...`')
    # We can use the details from the recently parsed IL18 party_detailed for this.
    data['party_simplified'] = data['party_detailed'].where(
        data['party_detailed'].isin({'DEMOCRAT', 'REPUBLICAN', 'NONPARTISAN',
                                     'LIBERTARIAN', ''}), 'OTHER')
    data['party_simplified'] = data['party_simplified'].str.replace('INDEPENDENT', 'NONPARTISAN')

    print('Parsed IL18 `party_simplified`.')
    return data


def make_mode(data: DataFrame) -> DataFrame:
    print('*Parsing IL18 `mode`...')
    # All vote totals are TOTAL
    data['mode'] = 'TOTAL'

    print('Parsed IL18 `mode`.')
    return data


def make_votes(data: DataFrame) -> DataFrame:
    print('*Parsing IL18 `votes...`')
    # Data is pulled straight from `Votes`
    data['votes'] = pd.to_numeric(data['Votes'], errors='raise')

    print('Parsed IL18 `votes`.')
    return data


def make_county_name(data: DataFrame) -> DataFrame:
    print('*Parsing IL18 `county_name`...')
    # Data is pulled straight from `County` and upper cased
    data['county_name'] = data['County'].str.upper()
    # We make a few replacements to align with county-fips-codes.csv
    data['county_name'] = data['county_name'].replace({
        'DEWITT': 'DE WITT',
        'JODAVIESS': 'JO DAVIESS',
        })

    print('Parsed IL18 `county_name`.')
    return data


def make_county_fips(data: DataFrame) -> DataFrame:
    print('*Parsing IL18 `county_fips`...')
    # Use recently obtained `county_name` field and list of county fips codes
    data['county_fips'] = EC.county_fips.parse_fips_from_name(data)

    print('Parsed IL18 `county_fips`.')
    return data


def make_jurisdiction_name(data: DataFrame) -> DataFrame:
    print('*Parsing IL18 `jurisdiction_name`...')
    # `jurisdiction_name` is the same as `county_name` for Illinois, so use that
    data['jurisdiction_name'] = data['county_name']

    print('Parsed IL18 `jurisdiction_name`.')
    return data


def make_jurisdiction_fips(data: DataFrame) -> DataFrame:
    print('*Parsing IL18 `jurisdiction_fips`...')
    # `jurisdiction_fips` is the same as `county_fips` for Illinois, so use that
    data['jurisdiction_fips'] = data['county_fips']

    print('Parsed IL18 `jurisdiction_fips`.')
    return data


def make_candidate(data: DataFrame) -> DataFrame:
    print('*Parsing IL18 `candidate...`')
    # Data is pulled from Candidate and uppercased
    data['candidate'] = data['Candidate'].str.upper()

    # First, remove any extraneous whitespace/characters
    data['candidate'] = data['candidate'].str.strip().replace({
        r' ( )+': ' ',
        r'\.': '',
        r',': '',
        r" '": ' "',  # Start of nickname
        r" \(": ' "',  # Start of nickname
        r'É':'E'}, regex=True)
    data['candidate'] = data['candidate'].str.strip().replace({
        r"' ": '" ',  # End of nickname
        r"\) ": '" ',
        r"’":"'",
        r"“":'"',
        r"”":'"',  # End of nickname
        }, regex=True)
    data['candidate'] = data['candidate'].str.replace('""','"',regex=True)
    # Standardize a few names
    data['candidate'] = data['candidate'].replace({
        r'OVER VOTES': 'OVERVOTES',
        r'UNDER VOTES': 'UNDERVOTES',
        r'WRITE-IN': 'WRITEIN',
        r'TOTAL':''
        # r'PHILL COLLINS': 'PHIL COLLINS',  # Typo
        # r'ANDRÉ THAPEDI': 'ANDRE THAPEDI',  # No accent marks

        # # A few counties listed the names backwards
        # r'CELLA TODD': 'TODD CELLA',
        # r'WELLS KASEY': 'KASEY WELLS',
        # r'CHARLES MARK': 'MARK CHARLES',
        # r'SHAWN HOWARD': 'HOWARD SHAWN',
        # r'SIMMONS JADE': 'JADE SIMMONS',
        # r'SEIDA LOWELL': 'LOWELL MARTIN SEIDA',
        # r'SEIDA LOWELL MARTIN': 'LOWELL MARTIN SEIDA',
        # r'ROUSE DEBORAH': 'DEBORAH ROUSE',
        # r'BELLAR BARBARA': 'BARBARA BELLAR',
        # r'ANDY HOPE WILLIAMS J$': 'ANDY HOPE WILLIAMS JR',
        }, regex=True)

    # standardize writein
    data.loc[data['candidate'].str.contains('753|SEVENFIVETHREE'), 'candidate'] = '753 JO'
    data.loc[data['candidate'].str.contains('CANFIELD'), 'candidate'] = 'Robert G "BOB" Canfield'.upper()
    data.loc[data['candidate'].str.contains('MOORE GREGG'), 'candidate'] = "GREGG MOORE"
    data.loc[data['candidate'].str.contains('FOSTER NANCY'), 'candidate'] = "NANCY FOSTER"
    data.loc[data['candidate'].str.contains('SCRUGGS'), 'candidate'] = "MICHAEL W SCRUGGS"
    data.loc[data['candidate'].str.contains('THOMAS J KUNA'), 'candidate'] = 'THOMAS "JACOB" J KUNA'
    data.loc[data['candidate'].str.contains('VANN-METCALF|VANN-METCAFF'), 'candidate'] = 'MARY ARLINE VANN-METCALF'
    data.loc[data['candidate'].str.contains('DAVID THOLIN'), 'candidate'] = 'DAVID A THOLIN'
    data.loc[data['candidate'].str.contains('KURT FOWLER|KURT SANTA FOWLER'), 'candidate'] = 'KURT "SANTA" FOWLER'

    # Standardize blanks, overvotes and undervotes for circuit court elections
    # We obtain the candidate's full name via the other candidate records they offer
    df_names = EC.split_column(data[['temp_office', 'candidate']], 'candidate',
                               r'(?P<candidate2>.*) - .*')
    df_names = df_names[['temp_office', 'candidate2']].dropna().drop_duplicates()
    names = df_names.set_index('temp_office').to_dict()['candidate2']
    targets = {
        'BLANK BALLOTS',
        'OVERVOTES',
        'UNDERVOTES',
        }
    data['candidate'] = data['candidate'].mask(
        (data['temp_office'].str.contains('RETAIN')) & (data['candidate'].isin(targets)),
        data['temp_office'].replace(names) + ' - ' + data['candidate']
        )

    # Now that we parsed retentions, we can now properly standardize them in office
    data = EC.adapt_column(data, 'temp_office',
                           r'CIRCUIT (?P<circuit>\d+)- RETAIN.*',
                           'RETENTION CIRCUIT COURT JUDGE: CIRCUIT {circuit}')
    data = EC.adapt_column(data, 'temp_office',
                           r'APPELLATE (?P<circuit>\d+)- RETAIN.*',
                           'RETENTION APPELLATE COURT JUDGE: {circuit}')
    data = EC.adapt_column(data, 'temp_office',
                           r'SUPREME (?P<circuit>\d+)- RETAIN.*',
                           'RETENTION SUPREME COURT JUSTICE: {circuit}')
    data = EC.adapt_column(data, 'temp_office',
                           r'COOK CIRCUIT- RETAIN.*',
                           'RETENTION COOK COUNTY CIRCUIT COURT JUDGE')

    # We now go with vacancies
    data = EC.adapt_column(data, 'temp_office',
                           r'CIRCUIT (?P<cir>\d+)- SUBCIRCUIT (?P<sub>\d+)- (?P<vacancy>.* VAC.*)',
                           'CIRCUIT COURT JUDGE - {vacancy}: CIRCUIT {cir} - SUBCIRCUIT {sub}'
                           )
    data = EC.adapt_column(data, 'temp_office',
                           r'CIRCUIT (?P<cir>\d+)- (?P<vacancy>.* VACANCY)',
                           'CIRCUIT COURT JUDGE - {vacancy}: CIRCUIT {cir}'
                           )
    data = EC.adapt_column(data, 'temp_office',
                           r'COOK CIRCUIT- (?P<vacancy>.* VACANCY)',
                           'COOK COUNTY CIRCUIT COURT JUDGE - {vacancy}'
                           )
    data = EC.adapt_column(data, 'temp_office',
                           r'COOK- SUBCIRCUIT (?P<sub>\d+)- (?P<vacancy>.* VACANCY)',
                           'COOK COUNTY SUBCIRCUIT COURT JUDGE - {vacancy}: {sub}'
                           )
    data = EC.adapt_column(data, 'temp_office',
                           r'APPELLATE (?P<cir>\d+)- (?P<vacancy>.* VACANCY)',
                           'APPELLATE COURT JUDGE - {vacancy}: {cir}'
                           )
    data = EC.adapt_column(data, 'temp_office',
                           r'SUPREME (?P<cir>\d+)- (?P<vacancy>.* VACANCY)',
                           'SUPREME COURT JUSTICE - {vacancy}: {cir}'
                           )

    # We will remove district mark later
    print('Parsed IL18 `candidate`.')
    print('Partially parsed IL18 `office` (2/3).')
    return data


def make_district(data: DataFrame) -> DataFrame:
    print('*Parsing IL18 `district`...')

    # Data is pulled from temp_office
    data = EC.split_column(data, 'temp_office',
                           '(?P<temp_office>.*): (?P<district>.*)',
                           maintaining_columns=['temp_office'],
                           empty_value=''
                           )
    data['office'] = data['temp_office']

    data['district'] = EC.district.mark_statewide_districts(
        data['district'], data['temp_office'], [
            'US SENATE',
            'GOVERNOR', 'SECRETARY OF STATE',
            'ATTORNEY GENERAL', 'COMPTROLLER', 'TREASURER',
            ])

    data['district'] = EC.district.fix_numerical_districts(data['district'])

    print('Parsed IL18 `district`.')
    print('Parsed IL18 `office` (3/3).')
    return data


def make_magnitude(data: DataFrame) -> DataFrame:
    print('*Parsing IL18 `magnitude`...')

    # Magnitude is 1 except for statistics
    data['magnitude'] = EC.iif(data['office'], lambda series: series.isin({
        'BALLOTS CAST',
        'REGISTERED VOTERS',
        }), 0, 1)

    print('Parsed IL18 `magnitude`.')
    return data


def make_dataverse(data: DataFrame) -> DataFrame:
    print('*Parsing IL18 `dataverse`...')

    data['dataverse'] = EC.dataverse.parse_dataverse_from_office(
        data['office'],
        state={
            'STATE HOUSE',
            'STATE SENATE',
            'GOVERNOR',
            "SECRETARY OF STATE"},
        empty={
            'BALLOTS CAST',
            'REGISTERED VOTERS',
            }
        )

    # As there are way too many judicial courts, we manually code dataverse for them
    data['dataverse'] = data['dataverse'].mask(
        data['office'].str.contains('|'.join({
            'APPELLATE COURT JUDGE',
            '^CIRCUIT COURT JUDGE',  # Use ^ to avoid matching SUBCIRCUIT JUDGE
            'COOK COUNTY CIRCUIT COURT JUDGE',
            'RETENTION CIRCUIT COURT JUDGE',
            'SUPREME COURT JUSTICE',
            'COMPTROLLER',
            'ATTORNEY GENERAL',
            'TREASURER'
            })),
        'STATE'
        )
    print('Parsed IL18 `dataverse`.')
    return data


def make_year(data: DataFrame) -> DataFrame:
    print('*Parsing IL18 `year`...')
    # Year is 2020 by definition
    data['year'] = 2018

    print('Parsed IL18 `year`.')
    return data


def make_stage(data: DataFrame) -> DataFrame:
    print('*Parsing IL18 `stage`...')
    # Election is consistently General
    data['stage'] = 'GEN'

    print('Parsed IL18 `stage`.')
    return data


def make_special(data: DataFrame) -> DataFrame:
    print('*Parsing IL18 `special`...')

    # The following are special elections
    # 1. Karmeier Vacancy for the Supreme Court
    # https://ballotpedia.org/Illinois_Supreme_Court_elections,_2020
    # 2. State Senate District 6 and 11
    # https://ballotpedia.org/Illinois_State_Senate_elections,_2020

    # data['special'] = EC.series_r_bool(
    #     (data['office'] == 'SUPREME COURT JUSTICE - KARMEIER VACANCY') |
    #     ((data['office'] == 'STATE SENATE') & (data['district'].isin({'006', '011'})))
    #     )
    data['special'] = 'FALSE'

    print('Parsed IL18 `special`.')
    return data


def make_writein(data: DataFrame) -> DataFrame:
    print('*Parsing IL18 `writein`...')
    # Illinois indicates writeins explicitly, except a few candidates named
    data['writein'] = EC.series_r_bool(data['candidate'].str.contains(r'WRITEIN'))
    data['writein'] = np.where(data['candidate'].isin(['753 JO', 'Robert G "BOB" Canfield'.upper(),
     "GREGG MOORE", "NANCY FOSTER","MICHAEL W SCRUGGS",'JUSTIN HANSON','KENNETH YERKES','RICHARD MAYERS']),
        'TRUE',data['writein'])
    #adjusting party problems too
    data.loc[data['writein']=='TRUE', 'party_detailed'] = ""
    data.loc[data['writein']=='TRUE', 'party_simplified'] = ""
    data.loc[((data['candidate'].str.contains('- YES|- NO')) & (data['party_simplified']=="")),
        'party_simplified'] = 'NONPARTISAN'
    data.loc[((data['candidate'].str.contains('- YES|- NO')) & (data['party_detailed']=="")),
        'party_detailed'] = 'NONPARTISAN'
    data.loc[data['candidate']=="",'party_detailed']=""
    data.loc[data['candidate']=="",'party_simplified']=""
    data.loc[data['candidate']=='DAVID K OVERSTREET','party_detailed'] = 'REPUBLICAN'
    data.loc[data['candidate']=='DAVID K OVERSTREET','party_simplified'] = 'REPUBLICAN'
    data.loc[data['candidate']=='BUBBA HARSY','party_detailed'] = 'LIBERTARIAN'
    data.loc[data['candidate']=='BUBBA HARSY','party_simplified'] = 'LIBERTARIAN'


    print('Parsed IL18 `writein`.')
    return data

def make_state_po(data: DataFrame) -> DataFrame:
    print('*Parsing IL18 `state_po`...')
    # Already parsed

    print('Parsed IL18 `state_po`.')
    return data


def make_state_fips(data: DataFrame) -> DataFrame:
    print('*Parsing IL18 `state_fips`...')
    # Already parsed

    print('Parsed IL18 `state_fips`.')
    return data


def make_state_cen(data: DataFrame) -> DataFrame:
    print('*Parsing IL18 `state_cen`...')
    # Already parsed

    print('Parsed IL18 `state_cen`.')
    return data


def make_state_ic(data: DataFrame) -> DataFrame:
    print('*Parsing IL18 `state_ic`...')
    # Already parsed

    print('Parsed IL18 `state_ic`.')
    return data


def make_date(data: DataFrame) -> DataFrame:
    print('*Parsing IL18 `date...`')

    # Illinois had one date for all elections
    data['date'] = '2018-11-06'

    print('*Parsed IL18 `date`.')
    return data


def make_readme_check(data: DataFrame) -> DataFrame:
    print('*Parsing IL18 `readme_check...`')

    # A few notes
    # 1. MCGLYNN appeared on the ballot for a retention election, but the results were not
    # officially erported.
    # 2. Official results report only certain individual writein candidates, while precinct data
    # only reports scatter.

    # data['readme_check'] = EC.series_r_bool((
    #     (data['candidate'].str.contains('MCGLYNN')) |
    #     (data['writein'] == 'TRUE')
    #     ))
    data['readme_check'] = np.where(data['precinct']=='COUNTY FLOATING',"TRUE",'FALSE')

    print('Parsed IL18 `readme_check`.')
    return data


if __name__ == '__main__':
    print("*Parsing raw data for Illinois...")
    raw_data = load_all_data(prepare_pickle=True)
    print("Parsed raw data for Illinois.")

    EC.check_original_dataset(
        raw_data,
        expected_columns={'County', 'Precinct', 'Office', 'Candidate', 'Party', 'Votes','preserve_juris'},
        county_column='County', expected_counties=102
        )

    data = raw_data.copy()
    # weird error within raw data where retain Deihl is not mapped to correct candidate
    data.loc[(data['Candidate'].str.upper() == 'DAVID R. CHERRY - NO')&
        (data['Office'].str.upper() == '7TH CIRCUIT - RETAIN DEIHL'), 'Candidate'] = 'KENNETH R. DEIHL - NO'
    # also one county contains exact duplicates, so drop before processing
    data = data.drop_duplicates()

    # Parse needed details for standard form
    data = make_state(data)
    data = make_precinct(data)
    data = make_office(data)
    data = make_party_detailed(data)
    data = make_party_simplified(data)
    data = make_mode(data)
    data = make_votes(data)
    data = make_county_name(data)
    data = make_county_fips(data)
    data = make_jurisdiction_name(data)
    data = make_jurisdiction_fips(data)

    # add back jurisdiction name to prevent duplicates in county agg. lets see...
    data['jurisdiction_name'] = data['preserve_juris'].str.upper()

    data = make_candidate(data)
    data = make_district(data)

    # candidates with nonpartisan party should have blank party in these offices
    writein_offices = ['US HOUSE','STATE SENATE',
           'GOVERNOR', 'STATE HOUSE',
           'COMPTROLLER', 'TREASURER',
           'ATTORNEY GENERAL',
            'SECRETARY OF STATE']

    data.loc[((data['office'].isin(writein_offices))&
        (data['party_detailed']=='NONPARTISAN')), 'party_simplified'] = ""
    data.loc[((data['office'].isin(writein_offices))&
        (data['party_detailed']=='NONPARTISAN')), 'party_detailed'] = ""
    data.loc[((data['office'].isin(writein_offices))&
        (data['party_detailed']=='')&
        (~data['candidate'].isin(['OVERVOTES', 'UNDERVOTES', 'BLANK BALLOTS']))), 'writein'] = "TRUE"

    data.loc[(data['candidate'].str.contains('OVERVOTES|UNDERVOTES')),'party_detailed'] =""
    data.loc[(data['candidate'].str.contains('OVERVOTES|UNDERVOTES')),'party_simplified'] =""

    data = make_magnitude(data)
    data = make_dataverse(data)
    data = make_year(data)
    data = make_stage(data)
    data = make_special(data)
    data = make_writein(data)
    data = make_state_po(data)
    data = make_state_fips(data)
    data = make_state_cen(data)
    data = make_state_ic(data)
    data = make_date(data)
    data = make_readme_check(data)
    data = data[~((data['precinct']=='COUNTY FLOATING')&(data['votes']==0))].copy()
    print('Parsed IL18 data.')
    data = EC.select_cleaned_dataset_columns(data, False)
    data = EC.sort_cleaned_dataset(data)
    EC.check_cleaned_dataset(data, expected_counties=102, expected_jurisdictions=108 ) # now retaining original juris info
    # EC.inspect_cleaned_dataset(data)
    EC.save_cleaned_dataset(data, '2018-il-precinct-general-updated.csv')
