import re
import json
import time
from datetime import datetime

from nba_api.stats.library.http import NBAStatsHTTP
from nba_api.stats.library.parameters import *

from tools.library.file_handler import load_file, save_file, get_file_path
from tools.stats.library.mapping import endpoint_list, parameter_variations, parameter_map

missing_parameter_regex = r"^\s*?(?:The value '[^']+' is not valid for |The )?([A-z0-9]+( Scope| Category)?)(?: Year)?\s*(?:property is required\.?| is required\.?(?:, pass 0 for default)?|\.)$"
# Season Year -> Season     This only occurs in LeagueDashPtStats

parameter_pattern_regex = r"\s*The field ([A-z]+) must match the regular expression '([^']+)'\.(?:;|$)"

missing_required_parameters = {
    'DefenseHub': {'Season': '2017-18'},
    'LeagueDashLineups': {'Season': Season.default},
    'LeagueDashPlayerClutch': {'Season': Season.default},
    'LeagueDashPlayerStats': {'Season': Season.default},
    'LeagueDashTeamClutch': {'Season': Season.default},
    'LeagueDashTeamShotLocations': {'Season': Season.default},
    'LeagueDashTeamStats': {'Season': Season.default},
    'LeagueGameLog': {'Counter': 0, 'Season': Season.default},
    'LeagueLeaders': {'Season': Season.default},
    'LeaguePlayerOnDetails': {'Season': Season.default, 'TeamID': '1610612739'},  # Cleveland Cavaliers
    'LeagueStandings': {'Season': Season.default},
    'PlayerCompare': {'Season': Season.default},
    'PlayerDashboardByClutch': {'Season': Season.default},
    'PlayerDashboardByGameSplits': {'Season': Season.default},
    'PlayerDashboardByGeneralSplits': {'Season': Season.default},
    'PlayerDashboardByLastNGames': {'Season': Season.default},
    'PlayerDashboardByOpponent': {'Season': Season.default},
    'PlayerDashboardByShootingSplits': {'Season': Season.default},
    'PlayerDashboardByTeamPerformance': {'Season': Season.default},
    'PlayerDashboardByYearOverYear': {'Season': Season.default},
    'PlayerDashPtPass': {'LeagueID': LeagueID.default},
    'PlayerDashPtReb': {'LeagueID': LeagueID.default},
    'PlayerDashPtShotDefend': {'LeagueID': LeagueID.default},
    'PlayerDashPtShots': {'LeagueID': LeagueID.default},
    'PlayerFantasyProfile': {'Season': Season.default},
    'PlayerFantasyProfileBarGraph': {'Season': Season.default},
    'PlayerVsPlayer': {'Season': Season.default},
    'ShotChartDetail': {'ContextMeasure': ContextMeasureSimple.default,'LeagueID': LeagueID.default, 'PlayerPosition': ''},
    'ShotChartLineupDetail': {'GameID': '', 'TeamID': ''},
    'TeamAndPlayersVsPlayers': {'Season': Season.default},
    'TeamDashboardByClutch': {'Season': Season.default},
    'TeamDashboardByGameSplits': {'Season': Season.default},
    'TeamDashboardByGeneralSplits': {'Season': Season.default},
    'TeamDashboardByLastNGames': {'Season': Season.default},
    'TeamDashboardByOpponent': {'Season': Season.default},
    'TeamDashboardByShootingSplits': {'Season': Season.default},
    'TeamDashboardByTeamPerformance': {'Season': Season.default},
    'TeamDashboardByYearOverYear': {'Season': Season.default},
    'TeamDashLineups': {'Season': Season.default},
    'TeamDashPtPass': {'LeagueID': LeagueID.default},
    'TeamDashPtReb': {'LeagueID': LeagueID.default},
    'TeamDashPtShots': {'LeagueID': LeagueID.default},
    'TeamPlayerDashboard': {'Season': Season.default},
    'TeamPlayerOnOffDetails': {'Season': Season.default},
    'TeamPlayerOnOffSummary': {'Season': Season.default},
    'TeamVsPlayer': {'Season': Season.default, 'TeamID': '1610612739'},  # Cleveland Cavaliers
    'VideoDetails': {'Season': Season.default},  # Cleveland Cavaliers
}

todo_list = {}


def add_todo_item(endpoint, item_type, prop, extras=False, extras_label=None):
    todo_list.setdefault(endpoint, {})
    todo_list[endpoint].setdefault(prop, {})
    todo_list[endpoint][prop].setdefault(item_type, {})

    if extras:
        todo_list[endpoint][prop][item_type].setdefault(extras_label, [])
        todo_list[endpoint][prop][item_type][extras_label].append(str(extras))


def print_todo_items(file_path, file_name):
    for endpoint, endpoint_data in todo_list.items():
        print(f"TODO items for {endpoint}:")
        for parameter, todo_item in endpoint_data.items():
            for item, extras in todo_item.items():
                if extras:
                    for extra_label, extra_value in extras.items():
                        print(f"\t{parameter}: {item} - {extra_label}: {' '.join(extra_value)}")
                else:
                    print(f"\t{parameter}: {item}")
    print(f'Check {get_file_path(file_path, file_name)} for more info about parameters.')


def get_patterns_from_response(nba_stats_response):
    parameter_patterns = {}

    if re.search('<.*?>', nba_stats_response.get_response()):  # HTML Response
        matches = []
    else:
        matches = nba_stats_response.get_response().split(';')
    for match in matches:
        parameter_regex_match = re.match(parameter_pattern_regex, match)
        invalid_parameter_match = re.match(missing_parameter_regex, match)
        prop = None
        pattern = None
        if parameter_regex_match:
            prop = parameter_regex_match.group(1)
            pattern = parameter_regex_match.group(2)
            prop = prop.replace(' ', '')
        elif invalid_parameter_match:
            prop = invalid_parameter_match.group(1)
            prop = prop.replace(' ', '')
        elif match in [' Invalid date', '<Error><Message>An error has occurred.</Message></Error>', 'Invalid game date',
                       ' Invalid game date']:
            pass
        elif nba_stats_response.valid_json():
            pass
        elif not parameter_regex_match and not invalid_parameter_match and 'Invalid date' not in nba_stats_response.get_response() and 'must be between' not in nba_stats_response.get_response():
            raise Exception('Failed to match error.', match)

        if prop:
            parameter_patterns[prop] = pattern

    return parameter_patterns


def get_required_parameters(endpoint, nba_stats_response):
    required_parameters = []
    if re.search('<.*?>', nba_stats_response.get_response()):  # Skip if HTML Response
        required_parameters_matches = []
    else:
        required_parameters_matches = nba_stats_response.get_response().split(';')
        if not required_parameters_matches:
            raise Exception('Failed to find matches.')
    for match in required_parameters_matches:
        required_parameter = re.match(missing_parameter_regex, match)
        if nba_stats_response.valid_json():
            continue
        elif not required_parameter:
            raise Exception('Failed to find required_parameter in match.', match)
        required_parameter = required_parameter.group(1).replace(' ', '')
        # Fix case sensitivity
        if required_parameter == 'Runtype':
            required_parameter = 'RunType'
        required_parameters.append(required_parameter)

    # Adding required parameters that need overriding
    if endpoint in missing_required_parameters:
        for parameter in missing_required_parameters[endpoint]:
            if parameter in required_parameters:
                continue
            required_parameters.append(parameter)
    return required_parameters


def required_parameters_test(endpoint):
    status = 'success'
    nba_stats_response = NBAStatsHTTP().send_api_request(endpoint=endpoint,  parameters={})

    required_parameters = get_required_parameters(endpoint, nba_stats_response)

    if '<title>NBA.com/Stats  | 404 Page Not Found </title>' in nba_stats_response.get_response():
        status = 'deprecated'
        return status, None, None, None

    required_params = {}
    required_params_errors = {}
    for prop in required_parameters:
        if prop in parameter_map:
            if len(parameter_map[prop]['non-nullable']):
                map_key = 'non-nullable'
            else:
                map_key = 'nullable'
            parameter_info_key = list(parameter_map[prop][map_key].values())[0]
            parameter_info = parameter_variations[parameter_info_key]
            required_params[prop] = parameter_info['parameter_value']
            required_params_errors[prop] = parameter_info['parameter_error_value']
        else:
            print(f'Property "{prop}" - required parameter; not found in parameter_map')
            add_todo_item(endpoint, 'Add to parameter_map', prop, extras=True, extras_label='Required parameter')
            status = 'invalid'
            required_params[prop] = '0'
            required_params_errors[prop] = 'a'

    return status, required_parameters, required_params, required_params_errors


def minimal_requirement_tests(endpoint, required_params, pause=1):
    status = 'success'
    all_parameters = list(required_params.keys())

    if endpoint in missing_required_parameters:
        for parameter, value in missing_required_parameters[endpoint].items():
            required_params[parameter] = value

    # 1. minimal requirement test with default non-nullable values
    nba_stats_response = NBAStatsHTTP().send_api_request(endpoint=endpoint, parameters=required_params)

    # 2. minimal requirement test with pattern matching
    if not nba_stats_response.valid_json():
        parameter_patterns = get_patterns_from_response(nba_stats_response=nba_stats_response)
        # Overwrites param with parameter patterns on mismatches.
        for prop in required_params.keys():
            if prop in parameter_patterns:
                pattern = parameter_patterns[prop]
                # Check if parameter is in parameter_map.
                try:
                    if pattern in parameter_map[prop]['non-nullable']:
                        map_key = 'non-nullable'
                    else:
                        map_key = 'nullable'
                    parameter_info_key = parameter_map[prop][map_key][pattern]
                except KeyError:
                    add_todo_item(endpoint, 'Add to parameter_map', prop=prop, extras=pattern,
                                  extras_label='parameter pattern')
                    parameter_info_key = prop
                # Check if parameter is in parameter_variations.
                try:
                    parameter_info = parameter_variations[parameter_info_key]
                    required_params[prop] = parameter_info['parameter_value']

                except KeyError:
                    add_todo_item(endpoint, 'Add to parameter_variations', prop=prop, extras=required_params[prop],
                                  extras_label='possible parameter_error_value')

        time.sleep(pause)
        nba_stats_response = NBAStatsHTTP().send_api_request(endpoint=endpoint, parameters=required_params)

    if nba_stats_response.valid_json():
        data_sets = nba_stats_response.get_headers_from_data_sets()
        all_parameters += list(nba_stats_response.get_parameters().keys())
    else:
        status = 'invalid'
        print(f"{endpoint}: {status}; failed to pass minimal values test")
        data_sets = {}
    all_parameters = list(set(all_parameters))

    # Update Parameter Pattern Mapping
    all_params = {}
    all_params_errors = {}
    for prop in all_parameters:
        if prop in parameter_map:
            if len(parameter_map[prop]['non-nullable']):
                map_key = 'non-nullable'
            else:
                map_key = 'nullable'
            parameter_info_key = list(parameter_map[prop][map_key].values())[0]
            parameter_info = parameter_variations[parameter_info_key]
            all_params[prop] = parameter_info['parameter_value']
            all_params_errors[prop] = parameter_info['parameter_error_value']
        else:
            print(f'Property "{prop}" - minimal test; not found in parameter_map')
            status = 'invalid'
            all_params[prop] = 'a'
            all_params_errors[prop] = 'a'
            add_todo_item(endpoint, 'Add to parameter_map', prop=prop)

    nullable_parameters = []
    if nba_stats_response.get_parameters():
        response_parameters = nba_stats_response.get_parameters()
        for parameter, value in response_parameters.items():
            if value is None or value is "":
                nullable_parameters.append(parameter)

        for parameter in all_parameters:
            if parameter in response_parameters.keys():
                continue
            if parameter in missing_required_parameters[endpoint] and missing_required_parameters[endpoint][parameter]:
                continue
            nullable_parameters.append(parameter)

        nullable_parameters = list(set(nullable_parameters))

    return status, all_parameters, data_sets, all_params_errors, nullable_parameters


def nullable_parameters_test(endpoint, all_parameters):
    skip_endpoints = ['boxscoreadvancedv2', 'boxscorefourfactorsv2', 'boxscoremiscv2', 'boxscorescoringv2',
                      'boxscoretraditionalv2', 'boxscoreusagev2', 'winprobabilitypbp']

    if endpoint.lower() in skip_endpoints:
        return []

    non_nullable_list = ['DefenseCategory']

    params = {prop: '' for prop in all_parameters if prop not in non_nullable_list and endpoint in missing_required_parameters and prop not in missing_required_parameters[endpoint]}
    nba_stats_response = NBAStatsHTTP().send_api_request(endpoint=endpoint, parameters=params)

    if 'An error has occurred.' in nba_stats_response.get_response() \
            or 'A value is required' in nba_stats_response.get_response():
        raise Exception('Failed to pass nullable parameters test. Possibly non-nullable value failing.')

    required_parameters = get_required_parameters(endpoint, nba_stats_response)
    nullable_parameters = [prop for prop in list(params.keys()) if prop not in required_parameters]
    if nba_stats_response.get_parameters():
        response_parameters = nba_stats_response.get_parameters()
        for parameter, value in response_parameters.items():
            if value is None or value is "":
                nullable_parameters.append(parameter)

        for parameter in all_parameters:
            if parameter in response_parameters.keys():
                continue
            if parameter in missing_required_parameters[endpoint] and missing_required_parameters[endpoint][parameter]:
                continue
            nullable_parameters.append(parameter)

    return nullable_parameters


def invalid_values_test(endpoint, all_params_errors):
    nba_stats_response = NBAStatsHTTP().send_api_request(endpoint=endpoint, parameters=all_params_errors)

    parameter_patterns = get_patterns_from_response(nba_stats_response=nba_stats_response)

    for param in list(all_params_errors.keys()):
        if param not in parameter_patterns:
            parameter_patterns[param] = None

    return parameter_patterns


def analyze_endpoint(endpoint, pause=1):
    # Testing endpoint with parameters that throw a require flag.
    status, required_parameters, required_params, required_params_errors = required_parameters_test(endpoint=endpoint)
    time.sleep(pause)

    # No need to continue if Endpoint is deprecated.
    if status == 'deprecated':
        return {'status': status, 'endpoint': endpoint, 'last_validated_date': str(datetime.now().date())}

    # Testing endpoint with the minimal amount of parameters required.
    status_test, all_parameters, data_sets, all_params_errors, nullable_parameters = \
        minimal_requirement_tests(endpoint=endpoint, required_params=required_params)
    time.sleep(pause)

    if status_test == 'invalid':
        status = status_test

    # Testing endpoint with all parameters with empty values to see which ones are allowed to be nullable.
    nullable_parameters += nullable_parameters_test(endpoint=endpoint, all_parameters=all_parameters)
    nullable_parameters = list(set(nullable_parameters))
    time.sleep(pause)

    # Testing endpoint with invalid values to grab matching patterns.
    parameter_patterns = invalid_values_test(endpoint=endpoint, all_params_errors=all_params_errors)

    if len(parameter_patterns) != len(all_parameters):
        print(f"{endpoint}: Length of patterns does not equal all our parameters.")
        print(f"Parameter Patters: {parameter_patterns}\nAll Parameters: {all_parameters}")
        status = 'invalid'

    all_parameters.sort()
    required_parameters.sort()
    nullable_parameters.sort()

    endpoint_analysis = {
        'status': status,
        'endpoint': endpoint,
        'parameters': all_parameters,
        'required_parameters': required_parameters,
        'nullable_parameters': nullable_parameters,
        'parameter_patterns': parameter_patterns,
        'data_sets': data_sets,
        'last_validated_date': str(datetime.now().date()),
    }

    return endpoint_analysis


def load_endpoint_file(file_path=None, file_name='analysis.json'):
    if not file_path:
        file_path = get_file_path(directory_name='endpoint_analysis')
    try:
        endpoints_information = json.loads(load_file(file_path=file_path, file_name=file_name))
    except FileNotFoundError:
        endpoints_information = {}
    except ValueError:
        raise Exception('Endpoint file is not in valid a JSON format.')

    return endpoints_information


def analyze_and_save_endpoints(endpoints=endpoint_list, file_path=None, file_name='analysis.json', pause=1):
    if not file_path:
        file_path = get_file_path(directory_name='endpoint_analysis')
    endpoints_information = load_endpoint_file(file_name=file_name, file_path=file_path)

    for endpoint in endpoints:
        if endpoint in endpoints_information and endpoints_information[endpoint]['status'] in ['success', 'deprecated']:
            print(f"{endpoint} already analyzed completely. Status: {endpoints_information[endpoint]['status']}")
            continue

        endpoint_analysis = analyze_endpoint(endpoint=endpoint, pause=pause)
        endpoints_information[endpoint] = endpoint_analysis
        time.sleep(pause)

        if endpoint not in endpoint_list and endpoint_analysis['status'] != 'deprecated':
            add_todo_item(endpoint, 'Add to endpoint_list', prop=endpoint)

        contents = json.dumps(endpoints_information, sort_keys=True, indent=4)
        save_file(file_path=file_path, file_name=file_name, contents=contents)
        print(f"Endpoint analysis for {endpoint} finished. Status: {endpoint_analysis['status']}")

    if todo_list:
        print_todo_items(file_path, file_name)
