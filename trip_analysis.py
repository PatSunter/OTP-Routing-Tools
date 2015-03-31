import sys
import csv
import os, os.path
from datetime import datetime, timedelta, time
import itertools
import json
import copy

from pyOTPA import geom_utils
from pyOTPA import time_utils
from pyOTPA import otp_config
from pyOTPA import Trip

########################
## Analysis and Printing

def get_trip_speed_direct(origin_lon_lat, dest_lon_lat, trip_req_start_dt,
        trip_itin):
    dist_direct = geom_utils.haversine(origin_lon_lat[0], origin_lon_lat[1],
        dest_lon_lat[0], dest_lon_lat[1])
    total_trip_sec = trip_itin.get_total_trip_sec(trip_req_start_dt)
    trip_speed_direct = (dist_direct / 1000.0) \
        / (total_trip_sec / (60 * 60.0))
    return trip_speed_direct

def calc_mean_total_time(trip_itins, trip_req_start_dts):
    sum_val = sum(itertools.imap(
        lambda trip_id: trip_itins[trip_id].get_total_trip_sec(
            trip_req_start_dts[trip_id]), trip_itins.iterkeys()))
    mean_sec = sum_val / float(len(trip_itins))
    return timedelta(seconds=mean_sec)

def calc_mean_basic_itin_attr(trip_itins, itin_attr):
    """Convenience function."""
    sum_val = sum(itertools.imap(
        lambda ti: ti.json[itin_attr], trip_itins.itervalues()))
    mean = sum_val / float(len(trip_itins))
    return mean

def calc_mean_init_waits(trip_itins, trip_req_start_dts):
    sum_val = timedelta(0)
    for trip_id, trip_itin in trip_itins.iteritems():
        trip_init_wait = trip_itin.get_init_wait_td(
            trip_req_start_dts[trip_id])
        sum_val += trip_init_wait    
    total_sec = time_utils.get_total_sec(sum_val)
    mean_sec = total_sec / float(len(trip_itins))
    return timedelta(seconds=mean_sec)

def calc_mean_tfer_waits(trip_itins):
    sum_val = timedelta(0)
    for trip_id, trip_itin in trip_itins.iteritems():
        trip_tfer_wait = trip_itin.get_tfer_wait_td()
        sum_val += trip_tfer_wait    
    total_sec = time_utils.get_total_sec(sum_val)
    mean_sec = total_sec / float(len(trip_itins))
    return timedelta(seconds=mean_sec)

def calc_mean_init_waits_by_mode(trip_itins, trip_req_start_dts):
    sum_modal_init_waits = {}
    cnt_modal_init_waits = {}
    for mode in otp_config.OTP_NON_WALK_MODES:
        sum_modal_init_waits[mode] = timedelta(0)
        cnt_modal_init_waits[mode] = 0
    for trip_id, trip_itin in trip_itins.iteritems():
        # Skip legs that are pure walking
        first_non_walk_mode = trip_itin.get_first_non_walk_mode()
        if first_non_walk_mode:
            trip_init_wait = trip_itin.get_init_wait_td(
                trip_req_start_dts[trip_id])
            sum_modal_init_waits[first_non_walk_mode] += trip_init_wait
            cnt_modal_init_waits[first_non_walk_mode] += 1
    mean_modal_init_waits = {}
    for mode in otp_config.OTP_NON_WALK_MODES:
        total_sec = time_utils.get_total_sec(sum_modal_init_waits[mode])
        mean_sec = total_sec / float(cnt_modal_init_waits[mode])
        mean_modal_init_waits[mode] = timedelta(seconds=mean_sec)
    return mean_modal_init_waits, cnt_modal_init_waits

def calc_mean_walk_dist_km(trip_itins):
    return calc_mean_basic_itin_attr(trip_itins, 'walkDistance') / 1000.0

def calc_mean_dist_travelled_km(trip_itins):
    sum_iter = itertools.imap(
        lambda ti: ti.get_dist_travelled(), trip_itins.itervalues())
    sum_dist_km = sum(sum_iter) / 1000.0
    mean_dist_travelled = sum_dist_km / float(len(trip_itins))
    return mean_dist_travelled

def calc_mean_transfers(trip_itins):
    # Can't use the standard mean-calculating algorithm here :- since OTP
    # returns a '-1' to distinguish pure-walking trips, from trips that have
    # only one transfer. We want to use zero for pure-walk trips for this mean
    # calculation, so adjust.
    tfer_vals = itertools.imap(
        lambda ti: ti.json['transfers'], trip_itins.itervalues())
    tfer_vals_adjust = itertools.imap(
        lambda tval: tval if tval >= 0 else 0, tfer_vals)
    mean = sum(tfer_vals_adjust) / float(len(trip_itins))
    return mean

def calc_mean_direct_speed(trip_itins, trips_by_id, trip_req_start_dts):
    sum_val = sum(itertools.imap(
        lambda trip_id: get_trip_speed_direct(trips_by_id[trip_id][0],
            trips_by_id[trip_id][1], trip_req_start_dts[trip_id],
            trip_itins[trip_id]), trip_itins.iterkeys()))
    mean_spd = sum_val / float(len(trip_itins))
    return mean_spd

def calc_num_trips_using_modes(trip_itins):
    modes_used_in_trip_counts = {}
    for mode in otp_config.OTP_MODES:
        modes_used_in_trip_counts[mode] = 0
    for trip_id, trip_itin in trip_itins.iteritems():
        modes_used = trip_itin.get_set_of_modes_used()
        for mode in modes_used:
            modes_used_in_trip_counts[mode] += 1
    return modes_used_in_trip_counts

def calc_total_legs_by_mode(trip_itins):
    num_legs_of_modes = {}
    for mode in otp_config.OTP_MODES:
        num_legs_of_modes[mode] = 0
    for trip_id, trip_itin in trip_itins.iteritems():
        mode_legs = trip_itin.get_mode_sequence()
        for mode in mode_legs:
            num_legs_of_modes[mode] += 1
    return num_legs_of_modes

def calc_sum_modal_distances(trip_itins):
    """Calculate the sum of OTP's reported in-vehicle travel distances,
    per-mode, over all trips."""
    sum_modal_distances = {}
    for mode in otp_config.OTP_MODES:
        sum_modal_distances[mode] = 0
    for trip_id, trip_itin in trip_itins.iteritems():
        trip_modal_dists = trip_itin.get_dist_m_by_mode()
        for mode, dist in trip_modal_dists.iteritems():
            sum_modal_distances[mode] += dist
    return sum_modal_distances

def calc_mean_modal_distances_per_all_trips(sum_modal_distances, n_trips_total):
    """Calculate the mean time, per-mode, over _all_ trips:- not just
    the ones where that mode was used."""
    means_modal_distances = {}
    for mode in otp_config.OTP_MODES:
        means_modal_distances[mode] = sum_modal_distances[mode] / \
            n_trips_total
    return means_modal_distances

def calc_mean_modal_distances_per_leg_used(sum_modal_distances,
        n_legs_per_mode):
    """Calculate the mean distance travelled, per-mode, over legs travelled on
    each mode."""
    means_modal_distances = {}
    for mode in otp_config.OTP_MODES:
        means_modal_distances[mode] = sum_modal_distances[mode] / \
            n_legs_per_mode[mode]
    return means_modal_distances

def calc_sum_modal_times(trip_itins):
    """Calculate the sum of in-vehicle travel time, per-mode, over all
    trips."""
    sums_modal_times = {}
    for mode in otp_config.OTP_MODES:
        sums_modal_times[mode] = 0
    for trip_id, trip_itin in trip_itins.iteritems():
        trip_modal_times = trip_itin.get_time_sec_by_mode()
        for mode, time_sec in trip_modal_times.iteritems():
            sums_modal_times[mode] += time_sec
    return sums_modal_times

def calc_mean_modal_times_per_all_trips(sums_modal_times, n_trips_total):
    """Calculate the mean time spent, per-mode, over _all_ trips:- not just the ones
    where that mode was used."""
    means_modal_times = {}
    for mode in otp_config.OTP_MODES:
        mean_time_s = sums_modal_times[mode] / \
            n_trips_total
        means_modal_times[mode] = timedelta(seconds=mean_time_s)
    return means_modal_times

def calc_mean_modal_times_per_leg_used(sums_modal_times, n_legs_per_mode):
    """Calculate the mean time spent, per-mode, over legs using that mode."""
    means_modal_times = {}
    for mode in otp_config.OTP_MODES:
        mean_time_s = sums_modal_times[mode] / \
            n_trips_total
        means_modal_times[mode] = timedelta(seconds=mean_time_s)
    return means_modal_times

def calc_mean_modal_speeds(trip_itins):
    sums_modal_speeds = {}
    n_modal_speeds = {}
    for mode in otp_config.OTP_MODES:
        sums_modal_speeds[mode] = 0
        n_modal_speeds[mode] = 0
    for trip_id, trip_itin in trip_itins.iteritems():
        trip_modal_times = trip_itin.get_time_sec_by_mode()
        trip_modal_dists = trip_itin.get_dist_m_by_mode()
        for mode in trip_modal_times.iterkeys():
            dist = trip_modal_dists[mode] 
            time_s = trip_modal_times[mode]
            if time_s > 0:
                speed_km_h = (dist / 1000.0) / (time_s / (60.0 * 60.0))
                sums_modal_speeds[mode] += speed_km_h
                n_modal_speeds[mode] += 1
            else:
                #print "Warning for trip %s: for mode %s: dist = %.2fm, "\
                #    "time = %.2fs (inf speed)" % (trip_id, mode, dist, time_s)
                #print "Not including this in the average."
                pass
    means_modal_speeds = {}
    for mode in otp_config.OTP_MODES:
        mean_spd_km_h = sums_modal_speeds[mode] / \
            float(n_modal_speeds[mode])
        means_modal_speeds[mode] = mean_spd_km_h
    return means_modal_speeds

TRIP_MEAN_HDRS = ['n trips', 'total time', 'init wait', 
    'direct speed (kph)', 'dist travelled (km)', 'walk dist (km)',
    'transfers']

TRIP_MEAN_HDRS_OUTPUT = ['n trips', 'total time (min)', 'init wait (min)', 
    'direct speed (kph)', 'dist travelled (km)', 'walk dist (km)',
    'transfers']

# Numbers of decimal places to round various outputs to.
OUTPUT_ROUND_DIST_KM = 3
OUTPUT_ROUND_SPEED_KPH = 2
OUTPUT_ROUND_TRANSFERS = 1
OUTPUT_ROUND_TIME_MIN = 2

def calc_means_of_tripset(trip_results, trips_by_id, trip_req_start_dts):
    means = {}
    means['n trips'] = len(trip_results)
    means['total time'] = \
        calc_mean_total_time(trip_results, trip_req_start_dts)
    means['init wait'] = \
        calc_mean_init_waits(trip_results, trip_req_start_dts)
    means['direct speed (kph)'] = \
        calc_mean_direct_speed(trip_results, trips_by_id,
            trip_req_start_dts)
    means['dist travelled (km)'] = calc_mean_dist_travelled_km(trip_results)
    means['walk dist (km)'] = calc_mean_walk_dist_km(trip_results) 
    means['transfers'] = calc_mean_transfers(trip_results)
    return means

def order_and_format_means_for_output(means_dict):
    means_ordered = [means_dict[TRIP_MEAN_HDRS[ii]] for ii in \
        range(len(TRIP_MEAN_HDRS))]
    means_ordered[TRIP_MEAN_HDRS.index('total time')] = \
        round(time_utils.get_total_mins(means_dict['total time']),
            OUTPUT_ROUND_TIME_MIN)
    means_ordered[TRIP_MEAN_HDRS.index('init wait')] = \
        round(time_utils.get_total_mins(means_dict['init wait']),
            OUTPUT_ROUND_TIME_MIN)
    means_ordered[TRIP_MEAN_HDRS.index('direct speed (kph)')] = \
        round(means_dict['direct speed (kph)'], OUTPUT_ROUND_SPEED_KPH)
    means_ordered[TRIP_MEAN_HDRS.index('dist travelled (km)')] = \
        round(means_dict['dist travelled (km)'], OUTPUT_ROUND_DIST_KM)
    means_ordered[TRIP_MEAN_HDRS.index('walk dist (km)')] = \
        round(means_dict['walk dist (km)'], OUTPUT_ROUND_DIST_KM)
    means_ordered[TRIP_MEAN_HDRS.index('transfers')] = \
        round(means_dict['transfers'], OUTPUT_ROUND_TRANSFERS)
    return means_ordered

def print_mean_results(mean_results_by_category, key_print_order=None):
    if key_print_order:
        keys = key_print_order
    else:
        keys = mean_results_by_category.keys()
        
    for key in keys:
        means = mean_results_by_category[key]
        if not means:
            print "  '%s': no results." % key
            continue     
        print "  '%s': %d trips, mean trip time %s, mean dist travelled "\
            "%.2fkm, direct speed %.2f km/h, "\
            "walk dist %.2fm, # of transfers %.1f" % \
             (key,
              means['n trips'],
              means['total time'],
              means['dist travelled (km)'],
              means['direct speed (kph)'],
              means['walk dist (km)'] * 1000.0,
              means['transfers'])
    print ""
    return

def categorise_trip_ids_by_first_non_walk_mode(trip_itins):
    trips_by_first_mode = {}
    for mode in otp_config.OTP_NON_WALK_MODES:
        trips_by_first_mode[mode] = {}
    for trip_id, trip_itin in trip_itins.iteritems():
        first_non_walk_mode = trip_itin.get_first_non_walk_mode()
        if first_non_walk_mode:
            trips_by_first_mode[first_non_walk_mode][trip_id] = trip_itin
    return trips_by_first_mode            

def categorise_trips_by_agencies_used(trip_itins):
    trips_by_agencies = {}
    for trip_id, trip_itin in trip_itins.iteritems():
        ag_set = trip_itin.get_set_of_agencies_used()
        # Turn this into a tuple of sorted agencies, so it is usable as a
        # dictionary key for classification.
        agencies = tuple(sorted(list(ag_set)))
        if agencies not in trips_by_agencies:
            trips_by_agencies[agencies] = {}
        trips_by_agencies[agencies][trip_id] = trip_itin
    return trips_by_agencies

def categorise_trip_results_by_od_sla(trip_itins, trips_by_id):
    trips_by_od_sla = {}
    for trip_id, trip_itin in trip_itins.iteritems():
        trip = trips_by_id[trip_id]
        o_sla, d_sla = trip[Trip.O_ZONE], trip[Trip.D_ZONE]
        if o_sla not in trips_by_od_sla:
            trips_by_od_sla[o_sla] = {}
        if d_sla not in trips_by_od_sla[o_sla]:
            trips_by_od_sla[o_sla][d_sla] = {}
        trips_by_od_sla[o_sla][d_sla][trip_id] = trip_itin
    return trips_by_od_sla

def categorise_trip_ids_by_mode_agency_route(trip_itins):
    trips_by_mar = {}
    trips_by_mar_legs = {}
    for mode in otp_config.OTP_NON_WALK_MODES:
        trips_by_mar[mode] = {}
        trips_by_mar_legs[mode] = {}
    for trip_id, trip_itin in trip_itins.iteritems():
        legs = trip_itin.json['legs']
        for leg_i, leg in enumerate(legs):
            mode = leg['mode']
            if mode == otp_config.OTP_WALK_MODE: continue
            a_name = leg['agencyName']
            r_id = leg['routeId']
            r_s_name = leg['routeShortName']
            r_l_name = leg['routeLongName']
            r_tup = (r_id, r_s_name, r_l_name)
            if a_name not in trips_by_mar[mode]:
                trips_by_mar[mode][a_name] = {}
                trips_by_mar_legs[mode][a_name] = {}
            if r_tup not in trips_by_mar[mode][a_name]:
                trips_by_mar[mode][a_name][r_tup] = {}
                trips_by_mar_legs[mode][a_name][r_tup] = {}

            trips_by_mar[mode][a_name][r_tup][trip_id] = \
                trip_itin
            if trip_id in trips_by_mar_legs[mode][a_name][r_tup]:
                trips_by_mar_legs[mode][a_name][r_tup][trip_id].append(leg_i)
            else:
                trips_by_mar_legs[mode][a_name][r_tup][trip_id] = [leg_i]
    return trips_by_mar, trips_by_mar_legs

def calc_save_trip_info_by_mode_agency_route(trip_itins, trip_req_start_dts, output_fname):

    trips_by_mar, trips_by_mar_legs = categorise_trip_ids_by_mode_agency_route(
        trip_itins)
    
    TRIP_INFO_BY_ROUTE_HEADERS = ['Mode', 'Agency', 'R ID', 'R S name', 
        'R L name', 'n trips', 'n legs', 'tot dist (km)', 'tot wait (min)',
        'mean dist/leg (km)', 'mean speed (km/h)', 'mean wait (min)']

    if sys.version_info >= (3,0,0):
        csv_file = open(output_fname, 'w', newline='')
    else:
        csv_file = open(output_fname, 'wb')

    writer = csv.writer(csv_file, delimiter=',')

    writer.writerow(TRIP_INFO_BY_ROUTE_HEADERS)

    for mode, trips_by_ar in trips_by_mar.iteritems():
        #print "For mode %s:" % mode
        for agency, trips_by_r in trips_by_ar.iteritems():
            #print "  for agency %s:" % agency
            out_row_base = [mode, agency]
            for route, trip_itins in trips_by_r.iteritems():
                r_id, r_short_name, r_l_name = route
                #print "    for route %s, %s:" % (r_short_name, r_l_name)
                sum_trips = len(trip_itins)
                sum_legs = 0
                sum_dist = 0
                sum_duration = 0
                sum_speeds_km_h = 0
                valid_speeds_cnt = 0
                mean_wait_min = 0
                sum_wait = timedelta(seconds=0)
                for trip_id, trip_itin in trip_itins.iteritems():
                    trip_req_start_dt = trip_req_start_dts[trip_id]
                    leg_is = trips_by_mar_legs[mode][agency][route][trip_id] 
                    sum_legs += len(leg_is)
                    for leg_i in leg_is:
                        leg_dist_m = trip_itin.json['legs'][leg_i]['distance'] 
                        leg_time_s = trip_itin.json['legs'][leg_i]['duration'] \
                            / 1000.0
                        wait = trip_itin.get_transfer_wait_before_leg(leg_i, 
                            trip_req_start_dt)
                        sum_wait += wait
                        sum_dist += leg_dist_m
                        sum_duration += leg_time_s
                        if leg_time_s > 0:
                            leg_speed_km_h = (leg_dist_m / 1000.0) \
                                / (leg_time_s / (60 * 60))
                            sum_speeds_km_h += leg_speed_km_h
                            valid_speeds_cnt += 1
                sum_dist_km = sum_dist / 1000.0            
                avg_dist_km = sum_dist / float(sum_legs) / 1000.0    
                mean_speed_km_h = sum_speeds_km_h / float(valid_speeds_cnt)
                sum_wait_min = time_utils.get_total_mins(sum_wait)
                mean_wait_min = sum_wait_min / float(sum_legs)
                #print "      Used in %d legs, %d trips, for %.2f km " \
                #    "(avg %.2f km/leg), at avg speed of %.2f km/hr" \
                #    % (sum_legs, sum_trips, sum_dist / 1000.0, \
                #       avg_dist_km, mean_speed_km_h)
                out_row = out_row_base + [r_id, r_short_name, r_l_name, \
                    sum_trips, sum_legs, 
                    round(sum_dist_km, OUTPUT_ROUND_DIST_KM), 
                    round(sum_wait_min, OUTPUT_ROUND_TIME_MIN), 
                    round(avg_dist_km, OUTPUT_ROUND_DIST_KM),
                    round(mean_speed_km_h, OUTPUT_ROUND_DIST_KM),
                    round(mean_wait_min, OUTPUT_ROUND_TIME_MIN)]
                writer.writerow(out_row)
            #print ""
    csv_file.close()
    return

def get_trip_req_start_dts(trips_by_id, trip_req_start_date):
    trip_req_start_dts = {}
    for trip_id, trip in trips_by_id.iteritems():
        if isinstance(trip[Trip.START_DTIME], datetime):
            trip_req_start_dts[trip_id] = trip[Trip.START_DTIME]
        else:
            trip_req_start_dts[trip_id] = datetime.combine(trip_req_start_date,
                trip[Trip.START_DTIME])
    return trip_req_start_dts

def get_trips_subset_by_ids(trip_results_dict, trip_ids_to_select):
    trip_results_filtered = {}
    for trip_id in trip_ids_to_select:
        try:
            trip_results_filtered[trip_id] = trip_results_dict[trip_id]
        except KeyError:
            raise ValueError("Input trip_results_dict didn't contain at "\
                "least one of the trip IDs ('%s') you requested in "\
                "trip_ids_to_select." % trip_id)
    return trip_results_filtered

def get_trips_subset_by_ids_to_exclude(trip_results_dict, trip_ids_to_exclude):
    # In the excluding IDs case:- start by creating a copy of the entire 
    # first dict:- since it will be faster to just delete dictionary entries
    # that are excluded. copy.copy just creates a new dictionary pointing to
    # the same actual entries in memory, so this won't waste lots of space.
    trip_results_filtered = copy.copy(trip_results_dict)
    for trip_id in trip_ids_to_exclude:
        try:
            del(trip_results_filtered[trip_id])
        except KeyError:
            print "Warning: Input trip_results_dict didn't contain at "\
                "least one of the trip IDs ('%s') you requested to exclude "\
                "in trip_ids_to_exclude." % trip_id
    return trip_results_filtered

def calc_means_of_tripset_by_first_non_walk_mode(trip_results_by_graph,
    trips_by_id, trip_req_start_dts):

    trips_by_first_non_walk_mode = {}
    means_by_first_non_walk_mode = {}
    for graph_name, trip_results in trip_results_by_graph.iteritems():
        if not trip_results:
            trips_by_first_non_walk_mode[graph_name] = None
            means_by_first_non_walk_mode[graph_name] = None
            continue
        # Further classify by first non-walk mode
        trips_by_first_non_walk_mode[graph_name] = \
            categorise_trip_ids_by_first_non_walk_mode(trip_results)
        means_by_first_non_walk_mode[graph_name] = {}
        for mode in otp_config.OTP_NON_WALK_MODES:
            means_by_first_non_walk_mode[graph_name][mode] = \
                calc_means_of_tripset(
                    trips_by_first_non_walk_mode[graph_name][mode],
                    trips_by_id, trip_req_start_dts)
    return means_by_first_non_walk_mode

def calc_print_mean_results_overall_summaries(
        graph_names, trip_results_by_graph, trips_by_id, trip_req_start_dts, 
        description=None):

    means = {}
    for graph_name in graph_names:
        trip_results = trip_results_by_graph[graph_name]
        if trip_results:
            means[graph_name] = calc_means_of_tripset(
                trip_results, trips_by_id, trip_req_start_dts)
        else:
            means[graph_name] = None

    if description:
        extra_string = "(%s)" % description
    else:
        extra_string = ""

    print "Overall %s mean results for the %d trips were:" \
        % (extra_string, max(map(len, trip_results_by_graph.itervalues())))
    print_mean_results(means)
    return

def calc_print_mean_results_agg_by_mode_agency(
        graph_names, trip_results_by_graph, trips_by_id, trip_req_start_dts, 
        description=None):

    sum_modes_in_trips = {}
    sum_legs_by_mode = {}
    sum_modal_dists = {}
    sum_modal_times = {}
    means_modal_times = {}
    means_modal_dists = {}
    means_modal_dist_leg = {}
    means_modal_speeds = {}
    means_init_waits_by_mode = {}
    counts_init_waits_by_mode = {}
    means_init_waits = {}
    means_tfer_waits = {}
    for graph_name in graph_names:
        trip_results = trip_results_by_graph[graph_name]
        if not trip_results: continue
        sum_modes_in_trips[graph_name] = \
            calc_num_trips_using_modes(trip_results)
        sum_legs_by_mode[graph_name] = \
            calc_total_legs_by_mode(trip_results)
        sum_modal_dists[graph_name] = \
            calc_sum_modal_distances(trip_results)
        sum_modal_times[graph_name] = \
            calc_sum_modal_times(trip_results)
        means_modal_times[graph_name] = \
            calc_mean_modal_times_per_all_trips(
                sum_modal_times[graph_name], len(trip_results))
        means_modal_dists[graph_name] = \
            calc_mean_modal_distances_per_all_trips(
                sum_modal_dists[graph_name], len(trip_results))
        means_modal_dist_leg[graph_name] = \
            calc_mean_modal_distances_per_leg_used(
                sum_modal_dists[graph_name], sum_legs_by_mode[graph_name])
        means_modal_speeds[graph_name] = \
            calc_mean_modal_speeds(trip_results)
        means_init_waits[graph_name] = \
            calc_mean_init_waits(trip_results, trip_req_start_dts)
        means_tfer_waits[graph_name] = \
            calc_mean_tfer_waits(trip_results)
    
    for graph_name, trip_results in trip_results_by_graph.iteritems():
        if not trip_results: continue
        miw_by_mode, ciw_by_mode = \
            calc_mean_init_waits_by_mode(trip_results,
                trip_req_start_dts)
        means_init_waits_by_mode[graph_name] = miw_by_mode
        counts_init_waits_by_mode[graph_name] = ciw_by_mode

    means_by_first_non_walk_mode = \
        calc_means_of_tripset_by_first_non_walk_mode(
            trip_results_by_graph, trips_by_id, trip_req_start_dts)

    trips_by_agencies_used = {}
    means_by_agencies_used = {}
    for graph_name in graph_names:
        # Further classify by agencies used
        trip_results = trip_results_by_graph[graph_name]
        if not trip_results: continue
        trips_by_agencies_used[graph_name] = \
            categorise_trips_by_agencies_used(trip_results)
        means_by_agencies_used[graph_name] = {}
        for agency_tuple, trip_itins in \
                trips_by_agencies_used[graph_name].iteritems():
            means_by_agencies_used[graph_name][agency_tuple] = \
                calc_means_of_tripset(trip_itins, trips_by_id,
                    trip_req_start_dts)

    if description:
        extra_string = " (%s)" % description
    else:
        extra_string = ""
    print "\nTrip results%s: aggregated by mode were:" % extra_string
    for graph_name in graph_names:
        trip_results = trip_results_by_graph[graph_name]
        if not trip_results: 
            print "(Graph %s had no results - skipping.)" % graph_name
            continue
        print "For graph %s, aggregated results for mode use were:" \
            % graph_name
        print "  mode, mean time (all trips), mean dist (all trips), "\
            "# trips used in, # legs, total dist (km), "\
            "mean dist/leg (m), mean in-vehicle speed (km/h)"
        for mode in otp_config.OTP_MODES:
            mode_time = means_modal_times[graph_name][mode]
            mode_dist = means_modal_dists[graph_name][mode]
            mode_in_trip_cnt = sum_modes_in_trips[graph_name][mode]
            mode_legs_cnt = sum_legs_by_mode[graph_name][mode]
            mode_sum_dist = sum_modal_dists[graph_name][mode]
            mode_dist_leg = means_modal_dist_leg[graph_name][mode]
            mode_speed = means_modal_speeds[graph_name][mode]
            print "  %s, %s, %.1f m, %d, %d, %.2f km, %.1f m, %.2f," \
                % (mode, mode_time, mode_dist, mode_in_trip_cnt, \
                   mode_legs_cnt, mode_sum_dist, mode_dist_leg, mode_speed)
        print "  initial wait, %s, " % means_init_waits[graph_name]
        print "  transfer wait, %s, " % means_tfer_waits[graph_name]

        print "\n  mean init waits, total trip times, trip overall speeds, "\
            "by first non-walk mode:"
        for mode in otp_config.OTP_NON_WALK_MODES:
            print "    %s: %s, %s, %.2f km/h (%d trips)" % (mode, \
                means_init_waits_by_mode[graph_name][mode],
                means_by_first_non_walk_mode[graph_name][mode]['total time'],
                means_by_first_non_walk_mode[graph_name][mode]['direct speed (kph)'],
                counts_init_waits_by_mode[graph_name][mode])
        print ""

        print "  mean init waits, total trip times, trip overall speeds, "\
            "by agencies used (sorted by speed):"
        agency_tups_and_means_sorted_by_spd = sorted(
            means_by_agencies_used[graph_name].iteritems(), 
            key = lambda x: x[1]['direct speed (kph)'])
        for agency_tuple, means in \
                reversed(agency_tups_and_means_sorted_by_spd):
            print "    %s: %s, %s, %.2f km/h (%d trips)" \
                % (agency_tuple, \
                   means['init wait'],
                   means['total time'],
                   means['direct speed (kph)'],
                   means['n trips'])
        print ""
    #import pdb
    #pdb.set_trace()

    return

def get_results_in_dep_time_range(trip_results, trip_req_start_dts,
        dep_time_info):
    trip_results_subset = {}
    for trip_id, trip_result in trip_results.iteritems():
        trip_start_dt = trip_req_start_dts[trip_id]
        if trip_start_dt.weekday() in dep_time_info[0] \
                and trip_start_dt.time() >= dep_time_info[1] \
                and trip_start_dt.time() < dep_time_info[2]:
            trip_results_subset[trip_id] = trip_result
    return trip_results_subset

def calc_save_trip_info_by_OD_SLA(trip_itins, trips_by_id, trip_req_start_dts,
        output_fname):

    tripsets_by_od_sla = categorise_trip_results_by_od_sla(trip_itins,
        trips_by_id)
    means_by_od_sla = {}
    for o_sla, tripsets_by_dest_sla in tripsets_by_od_sla.iteritems():
        means_by_od_sla[o_sla] = {}
        for d_sla, trip_itins in tripsets_by_dest_sla.iteritems():
            means_by_od_sla[o_sla][d_sla] = calc_means_of_tripset(
                trip_itins, trips_by_id, trip_req_start_dts)
    
    if sys.version_info >= (3,0,0):
        csv_file = open(output_fname, 'w', newline='')
    else:
        csv_file = open(output_fname, 'wb')

    TRIP_MEANS_BY_OD_HDRS = ['Origin SLA', 'Dest SLA'] \
        + TRIP_MEAN_HDRS_OUTPUT
    writer = csv.writer(csv_file, delimiter=',')
    writer.writerow(TRIP_MEANS_BY_OD_HDRS)

    for o_sla, means_by_d_sla in means_by_od_sla.iteritems():
        for d_sla, means in means_by_d_sla.iteritems():
            out_row_base = [o_sla, d_sla]
            means_ordered = order_and_format_means_for_output(means)
            out_row = out_row_base + means_ordered
            writer.writerow(out_row)
    csv_file.close()
    return

def calc_print_mean_results_by_dep_times(graph_names, trip_results_by_graph,
        trips_by_id, trip_req_start_dts,
        dep_time_cats, description=None,
        dep_time_print_order=None ):
    """Similar to the normal mean-printing function:- but this time breaks
    down results into categories based on departure times.
    These are given by input dictionary 'dep_time_cats': with each entry
    being key being a time category string (e.g. 'weekday_morning_early')
    mapped to a tuple of the form:
    (dow_list, time_start, time_end)
    * dow_list is a list of days-of-the-week matching the Python datetime
      class's weekday() function :- where 0 is Monday, etc.
    * time_start and time_end are both Python time instances listing when that
      time category begins and ends.
    * E.g. here is a tuple for weekday evenings between 6:30PM and midnight:
    ([0,1,2,3,4], time(18,30), time(23,59,59))   
    """

    means_by_deptime = {}
    for graph_name in graph_names:
        trip_results = trip_results_by_graph[graph_name]
        if not trip_results:
            means_by_deptime[graph_name] = None
            continue
        means_by_deptime[graph_name] = {}
        for dep_time_cat, dt_info in dep_time_cats.iteritems():
            trip_results_for_dep_time_cat = get_results_in_dep_time_range(
                trip_results, trip_req_start_dts, dt_info)
            if trip_results_for_dep_time_cat:
                means_by_deptime[graph_name][dep_time_cat] = \
                    calc_means_of_tripset(
                        trip_results_for_dep_time_cat, trips_by_id,
                        trip_req_start_dts)
            else:
                # In case there's no results in that time period
                means_by_deptime[graph_name][dep_time_cat] = None

    if description:
        extra_string = " (%s)" % description
    else:
        extra_string = ""
    print "\nMean results for the %d trips%s, by departure time period, were:" \
        % (max(map(len, trip_results_by_graph.itervalues())), extra_string)
    for graph_name in graph_names:
        print "For graph name '%s':" % graph_name
        if not trip_results_by_graph[graph_name]:
            print "(No results)."
            continue
        print_mean_results(means_by_deptime[graph_name], dep_time_print_order)
    return        

def createTripsCompShapefile(trips_by_id, graph_names, trip_req_start_dts,
        trip_results_1, trip_results_2, shapefilename):
    """Creates a Shape file stating the difference between times in two
    sets of results for the same set of trips.
    Saves results to a shapefile determined by shapefilename.
    
    N.B. :- thanks for overall strategy here are due to author of
    https://github.com/glennon/FlowpyGIS"""

    import osgeo.ogr
    from osgeo import ogr

    print "Creating shapefile of trip lines with time attributes to file"\
        " %s ..." % (shapefilename)

    driver = ogr.GetDriverByName('ESRI Shapefile')
    # create a new data source and layer
    if os.path.exists(shapefilename):
        driver.DeleteDataSource(shapefilename)
    ds = driver.CreateDataSource(shapefilename)
    if ds is None:
        print 'Could not create file'
        sys.exit(1)

    c1TimeFieldName = 't%s' % graph_names[0]
    c2TimeFieldName = 't%s' % graph_names[1]
    #Abbreviate due to Shpfile limits.
    c1TimeFieldName = c1TimeFieldName[:8]
    c2TimeFieldName = c2TimeFieldName[:8]

    layer = ds.CreateLayer('trip_comps', geom_type=ogr.wkbLineString)
    fieldDefn = ogr.FieldDefn('TripID', ogr.OFTString)
    fieldDefn.SetWidth(20)
    layer.CreateField(fieldDefn)
    fieldDefn = ogr.FieldDefn('DepTime', ogr.OFTString)
    fieldDefn.SetWidth(8)
    layer.CreateField(fieldDefn)
    fieldDefn = ogr.FieldDefn('OriginZ', ogr.OFTString)
    fieldDefn.SetWidth(254)
    layer.CreateField(fieldDefn)
    fieldDefn = ogr.FieldDefn('DestZ', ogr.OFTString)
    fieldDefn.SetWidth(254)
    layer.CreateField(fieldDefn)
    fieldDefn = ogr.FieldDefn(c1TimeFieldName, ogr.OFTInteger)
    layer.CreateField(fieldDefn)
    fieldDefn = ogr.FieldDefn(c2TimeFieldName, ogr.OFTInteger)
    layer.CreateField(fieldDefn)
    fieldDefn = ogr.FieldDefn('Diff', ogr.OFTInteger)
    layer.CreateField(fieldDefn)
    # END setup creation of shapefile

    for trip_id in sorted(trips_by_id.iterkeys()):
        trip = trips_by_id[trip_id]
        trip_req_start_dt = trip_req_start_dts[trip_id]

        try:
            trip_res_1 = trip_results_1[trip_id]
            trip_res_2 = trip_results_2[trip_id]
        except KeyError:
            # For now - just skip trips not valid in both graphs.
            continue
        case1time = trip_res_1.get_total_trip_sec(trip_req_start_dt)
        case2time = trip_res_2.get_total_trip_sec(trip_req_start_dt)
        linester = ogr.Geometry(ogr.wkbLineString)
        linester.AddPoint(*trip[Trip.ORIGIN])
        linester.AddPoint(*trip[Trip.DEST])

        featureDefn = layer.GetLayerDefn()
        feature = ogr.Feature(featureDefn)
        feature.SetGeometry(linester)
        feature.SetField('TripId', str(trip_id))
        feature.SetField('DepTime', trip[Trip.START_DTIME].strftime('%H:%M:%S'))
        feature.SetField('OriginZ', trip[Trip.O_ZONE])
        feature.SetField('DestZ', trip[Trip.D_ZONE])
        feature.SetField(c1TimeFieldName, case1time)
        feature.SetField(c2TimeFieldName, case2time)
        diff = case1time - case2time
        feature.SetField('Diff', diff)
        layer.CreateFeature(feature)

    # shapefile cleanup
    # destroy the geometry and feature and close the data source
    linester.Destroy()
    feature.Destroy()
    ds.Destroy()
    print "Done."
    return
