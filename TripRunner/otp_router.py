"""Module to run selected trips in OTP."""

import urllib
import urllib2
import socket
import os.path
import json
import copy
import time
from datetime import datetime

from pyOTPA import otp_config
from pyOTPA import Trip
from pyOTPA import TripItinerary

PROGRESS_PRINT_PERCENTAGE = 1

MAX_SECONDS_TO_WAIT_FOR_RESULT = 30
ROUTE_RETRIES = 2
SECONDS_TO_WAIT_BEFORE_RETRY = 10
MAX_ALLOWED_FAIL_TO_GET_RESULT = 10

def build_trip_spec_url_section(routing_params, trip_date,
        trip_time, origin_lon_lat, dest_lon_lat):
    tripReqStr = ""
    date_str = trip_date.strftime(otp_config.OTP_DATE_FMT)
    time_str = trip_time.strftime(otp_config.OTP_TIME_FMT)
    # General OTP routing request stuff
    tripReqStr += "&".join([name+'='+urllib2.quote(str(val)) for name, val \
        in routing_params.iteritems()])
    tripReqStr += '&'+'fromPlace'+'='+str(origin_lon_lat[1]) \
        + ','+str(origin_lon_lat[0])
    tripReqStr += '&'+'toPlace'+'='+str(dest_lon_lat[1])+','+str(dest_lon_lat[0])
    tripReqStr += '&'+'time'+'='+date_str+'T'+urllib2.quote(time_str)
    return tripReqStr

def build_trip_web_planner_app_url(base_web_app_url, routing_params, trip_date,
        trip_time, origin_lon_lat, dest_lon_lat, otp_router_id=None):
    reqStr = "/#/submit"
    reqStr += '&' 
    tripReqStr = ""
    date_str = trip_date.strftime(otp_config.OTP_DATE_FMT_WEB_PLANNER)
    time_str = trip_time.strftime(otp_config.OTP_TIME_FMT_WEB_PLANNER)
    time_str = time_str.lower().lstrip('0')
    # General OTP routing request stuff
    tripReqStr += "&".join([name+'='+urllib2.quote(str(val)) for name, val \
        in routing_params.iteritems()])
    tripReqStr += '&'+'fromPlace'+'='+str(origin_lon_lat[1]) \
        + ','+str(origin_lon_lat[0])
    tripReqStr += '&'+'toPlace'+'='+str(dest_lon_lat[1])+','+str(dest_lon_lat[0])
    tripReqStr += '&'+'date'+'='+date_str
    tripReqStr += '&'+'time'+'='+time_str
    reqStr += tripReqStr
    url = base_web_app_url + reqStr
    return url

def build_trip_request_url(server_url, routing_params, trip_date, trip_time,
        origin_lon_lat, dest_lon_lat, otp_router_id=None):
    date_str = trip_date.strftime(otp_config.OTP_DATE_FMT)
    time_str = trip_time.strftime(otp_config.OTP_TIME_FMT)

    reqStr = "/opentripplanner-api-webapp/ws" + "/plan" + '?'
    reqStr += build_trip_spec_url_section(routing_params, trip_date,
        trip_time, origin_lon_lat, dest_lon_lat) 
    if otp_router_id is not None:
        reqStr += '&'+'routerId'+'='+otp_router_id
    # Add server URL
    url = server_url + reqStr
    return url

def route_trip(server_url, routing_params, trip_req_start_date,
        trip_req_start_time, origin_lon_lat, dest_lon_lat, otp_router_id,
        server_timeout=MAX_SECONDS_TO_WAIT_FOR_RESULT):

    url = build_trip_request_url(server_url, routing_params,
        trip_req_start_date, 
        trip_req_start_time, origin_lon_lat, dest_lon_lat,
        otp_router_id)
    #print url

    data = None
    try:
        response = urllib2.urlopen(url, timeout=server_timeout)
        data = response.read()
    except urllib2.URLError:
        # In case of timeouts etc:- just return no data.
        data = None
    except socket.timeout:
        # In some cases this different exception is how timeouts raised
        # see http://heyman.info/2010/apr/22/python-urllib2-timeout-issue/
        data = None
    return data

def route_single_trip_multi_graphs_print_stats(server_url, routing_params,
        graph_specs, trip_req_start_date, trip_req_start_time,
        origin_lon_lat, dest_lon_lat):    
    trip_req_start_dt = datetime.combine(trip_req_start_date,
        trip_req_start_time)

    print "\nCalling server to route a trip from %s to %s, leaving "\
        "at %s:" % (origin_lon_lat, dest_lon_lat, trip_req_start_dt)

    for graph_name, graph_full in graph_specs.iteritems():
        res_str = route_trip(server_url, routing_params,
            trip_req_start_date, trip_req_start_time, origin_lon_lat,
            dest_lon_lat, otp_router_id=graph_full)
        if res_str:
            res = json.loads(res_str)
            #import pprint
            #pp = pprint.PrettyPrinter(indent=2)
            #pp.pprint(res)
            itin_json = res['plan']['itineraries'][0]
            print "\nRouting on the %s network/timetable, Requested trip stats:" \
                % graph_name
            ti = TripItinerary.TripItinerary(itin_json)
            TripItinerary.print_single_trip_stats(origin_lon_lat, dest_lon_lat,
                trip_req_start_dt, ti)
        else:
            print "\nRouting on the %s network/timetable trip from %s to %s "\
                "at %s :- failed to route." \
                    % (origin_lon_at, dest_lon_lat, trip_req_start_dt)
    return

def route_trip_set_on_graphs(server_url, routing_params,
        graph_specs, trips, trips_by_id, output_base_dir,
        trip_req_start_date=None, 
        save_incrementally=True, resume_existing=False):
    """Note:- by default trips should have a datetime specified now. But if
    not and trip_req_start_date is set, will use this date."""

    trip_results_by_graph = {}
    trips_to_route = None
    if not trip_req_start_date:
        trips_to_route = copy.copy(trips_by_id)
    else:
        trips_to_route = {}
        for trip_id, trip in trips_by_id.iteritems():
            if not isinstance(trip[Trip.START_DTIME], datetime):
                trip_dt = datetime.combine(trip_req_start_date,
                    trip[Trip.START_DTIME])
                trips_to_route[trip_id] = Trip.new_trip_with_updated_start(
                    trip, trip_dt)
            else:
                trips_to_route[trip_id] = trip

    for graph_name, graph_full in graph_specs.iteritems():
        output_subdir = os.path.join(output_base_dir, graph_name)
        if save_incrementally:
            if not os.path.exists(output_subdir):
                os.makedirs(output_subdir)

        print "\nRouting the %d requested trips on the %s network/timetable: " \
            % (len(trips_to_route), graph_name)
        trip_results = {}
        trips_routed = 0
        trips_processed = 0
        trips_failed_to_get_result = 0
        print_increment = len(trips_to_route) * (PROGRESS_PRINT_PERCENTAGE / 100.0)
        next_print_total = print_increment
        sorted_trips_to_route = sorted(trips_to_route.iteritems())
        for trip_ii, trip_tuple in enumerate(sorted_trips_to_route):
            trip_id, trip = trip_tuple
            output_fname = os.path.join(output_subdir, "%s.json" % trip_id)
            output_fname_next = None
            if trip_ii < len(sorted_trips_to_route) - 1:
                next_id = sorted_trips_to_route[trip_ii+1][0]
                output_fname_next = os.path.join(output_subdir,
                    "%s.json" % next_id)

            if resume_existing and os.path.exists(output_fname):
                trips_processed += 1
            elif resume_existing and output_fname_next \
                    and os.path.exists(output_fname_next):
                trips_processed += 1    
            else:
                trip_req_start_dt = trip[Trip.START_DTIME]
                trip_req_start_date = trip_req_start_dt.date()
                trip_req_start_time = trip_req_start_dt.time()
                res_str = None
                retries_remain = ROUTE_RETRIES
                while not res_str and retries_remain > 0:
                    res_str = route_trip(server_url, routing_params,
                        trip_req_start_date, trip_req_start_time,
                        trip[Trip.ORIGIN],
                        trip[Trip.DEST],
                        otp_router_id=graph_full)
                    if not res_str:
                        retries_remain -= 1
                        time.sleep(SECONDS_TO_WAIT_BEFORE_RETRY)
                if not res_str:
                    print "\tWarning:- requested trip ID %s from %s to %s at "\
                        "%s time on graph %s failed to route, after %d "\
                        "retries. "\
                        % (str(trip_id), trip[Trip.ORIGIN], trip[Trip.DEST],
                           trip[Trip.START_DTIME], graph_name,
                           ROUTE_RETRIES)
                    trips_processed += 1           
                    trips_failed_to_get_result += 1
                else:
                    res = json.loads(res_str)
                    if not res['plan']:
                        print "\tWarning:- requested trip ID %s from %s to "\
                            "%s at %s time on graph %s failed to generate "\
                            "valid itererary. "\
                            "Error msg returned by OTP router was:\n\t\t%s"\
                            % (str(trip_id), trip[Trip.ORIGIN], trip[Trip.DEST],
                               trip[Trip.START_DTIME],
                               graph_name, res['error']['msg'])
                        ti = None
                    else:    
                        try:
                            itin_json = res['plan']['itineraries'][0]
                            ti = TripItinerary.TripItinerary(itin_json)
                        except TypeError, IndexError:
                            print "Unexpected failure to get trip itinerary "\
                                "from received result."
                            ti = None
                    trip_results[trip_id] = ti    
                    if ti and save_incrementally:
                        ti.save_to_file(output_fname)
                    #print "\nTrip from %s to %s, leaving at %s:" \
                    #   % (trip[Trip.ORIGIN], trip[Trip.DEST],
                    #      trip_req_start_dt)
                    #TripItinerary.print_single_trip_stats(
                    #    trip[Trip.ORIGIN], trip[Trip.DEST],
                    #    trip_req_start_dt, ti)
                    trips_routed += 1
                    trips_processed += 1

            if trips_processed >= next_print_total:
                while trips_processed >= next_print_total:
                    next_print_total += print_increment
                percent_done = trips_processed / \
                    float(len(trips_to_route)) * 100.0
                print "...processed %d trips (%.1f%% of total.)" \
                    % (trips_processed, percent_done)
            if trips_failed_to_get_result >= MAX_ALLOWED_FAIL_TO_GET_RESULT:
                print "Error:- %d trips on graph %s failed to get a routing "\
                    "result back from server at URL %s:- giving up." \
                    % (trips_failed_to_get_result, graph_name, server_url)
                break
        trip_results_by_graph[graph_name] = trip_results
    return trip_results_by_graph
    

