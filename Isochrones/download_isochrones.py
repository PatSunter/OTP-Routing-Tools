#!/usr/bin/env python2

import urllib
import urllib2
import os.path

import utils

"""A Python script to help download a series of Isochrone files from
an OpenTripPlanner server"""

def buildRequestStringRaster(server_url, routing_params, date, time, lon_lat,
        img_bbox, raster_res, otp_router_id=None):
    reqStr = "/opentripplanner-api-webapp/ws" + "/wms" + '?'
    # General OTP routing request stuff
    reqStr += "&".join([name+'='+urllib2.quote(str(val)) for name, val \
        in routing_params.iteritems()])
    reqStr += '&'+'fromPlace'+'='+str(lon_lat[1])+','+str(lon_lat[0])
    reqStr += '&'+'toPlace'+'='+str(lon_lat[1])+','+str(lon_lat[0])
    reqStr += '&'+'time'+'='+date+'T'+urllib2.quote(time)
    # Stuff specific to raster output
    reqStr += '&'+'format'+'='+"image/geotiff"
    reqStr += '&'+'srs'+'='+"EPSG:4326"
    reqStr += '&'+'resolution'+'='+str(raster_res)
    reqStr += '&'+'bbox'+'='+','.join(str(ii) for ii in img_bbox[0] + \
        img_bbox[1])
    if otp_router_id is not None:
        reqStr += '&'+'routerId'+'='+otp_router_id
    # Add server URL
    url = server_url + reqStr
    return url

def buildRequestStringVector(server_url, routing_params, date, time, lon_lat,
        time_radius, vec_type, otp_router_id=None):
    reqStr = "/opentripplanner-api-webapp/ws" + "/iso" + '?'
    # General OTP routing request stuff
    reqStr += "&".join([name+'='+urllib2.quote(str(val)) for name, val \
        in routing_params.iteritems()])
    reqStr += '&'+'fromPlace'+'='+str(lon_lat[1])+','+str(lon_lat[0])
    reqStr += '&'+'toPlace'+'='+str(lon_lat[1])+','+str(lon_lat[0])
    reqStr += '&'+'time'+'='+date+'T'+urllib2.quote(time)
    # Stuff specific to raster output
    reqStr += '&'+'walkTime'+'='+str(time_radius)
    reqStr += '&'+'output'+'='+vec_type
    if otp_router_id is not None:
        reqStr += '&'+'routerId'+'='+otp_router_id
    # Add server URL
    url = server_url + reqStr
    return url

def saveIsosForLocations(server_url, otp_router_id, save_path,
        save_suffix, locations, date, times,
        save_nearby_times, nearby_minutes, num_each_side,
        routing_params, 
        raster_bounding_buf, raster_res,
        iso_inc, iso_max, vec_types, re_download=False):

    if os.path.exists(save_path) is False: 
        os.makedirs(save_path)

    for loc in locations:
        loc_name_orig = loc[0]
        lon_lat = loc[1]
        img_buf = raster_bounding_buf
        img_bbox = [(lon_lat[0] - img_buf[0], lon_lat[1] - img_buf[1]),
            (lon_lat[0] + img_buf[0], lon_lat[1] + img_buf[1])]

        print "Saving info for location %s" % loc_name_orig
        for time in times:
            print "For time %s:" % time
            if save_nearby_times is None:
                mins_diffs = 0
            else:
                mins_diffs = utils.get_nearby_min_diffs(nearby_minutes,
                    num_each_side)

            date_time_str_set = utils.get_date_time_string_set(date, time,
                mins_diffs)
            fname_set = utils.get_raster_filenames(loc_name_orig,
                date_time_str_set, save_path, save_suffix)

            print "About to save rasters at dates and times, to files:"
            for date_time_tuple, fname in zip(date_time_str_set, fname_set):
                date_mod, time_mod = date_time_tuple
                if re_download or not os.path.exists(fname):
                    print "   %s - %s -> %s" % (date_mod, time_mod, fname) 

            for date_time_tuple, fname in zip(date_time_str_set, fname_set):
                if re_download or not os.path.exists(fname):
                    date_mod, time_mod = date_time_tuple
                    url = buildRequestStringRaster(server_url, routing_params,
                        date_mod, time_mod, lon_lat, img_bbox, raster_res,
                        otp_router_id)
                    print url
                    response = urllib2.urlopen(url)
                    data = response.read()
                    f = open(fname, "w")
                    f.write(data)
                    f.close()

            # Now get the vectors, at different time radius.
            # TODO: Remove once iso issue debugged successfully on NECTAR
            # server.
            continue
            print "About to save vectors:"
            isochrones = range(iso_inc, iso_max+1, iso_inc)
            for iso in isochrones:
                for vec_type in vec_types:
                    vec_fname = utils.vectorName(loc_name_orig, time, iso, vec_type,
                        save_path, save_suffix)
                    if re_download or not os.path.exists(vec_fname):
                        url = buildRequestStringVector(server_url, routing_params, 
                            date, time, lon_lat, iso, vec_type, otp_router_id)
                        print url
                        response = urllib2.urlopen(url)
                        data = response.read()
                        f = open(vec_fname, "w")
                        f.write(data)
                        f.close()
            print "DONE!\n"
    return

def save_isos(multi_graph_iso_set, re_download=False):
    for server_url, otp_router_id, save_path, save_suffix, isos_spec in \
            multi_graph_iso_set:
        saveIsosForLocations(server_url, otp_router_id, save_path,
            save_suffix, re_download=re_download, **isos_spec)

def load_locations_from_shpfile(shpfile_name):
    """Desired output format is a list of tuples containing a location name,
    and a lon, lat pair, e.g.:
    ("MONASH UNI CLAYTON", (145.13163, -37.91432))"""
    locations = []

    output_srs = osr.SpatialReference()
    output_srs.ImportFromEPSG(OTP_ROUTER_EPSG)

    locations_shp = ogr.Open(shpfile_name, 0)
    if locations_shp is None:
        print "Error, input locations shape file given, %s , failed to open." \
            % (shpfile_name)
        sys.exit(1)
    locations_lyr = locations_shp.GetLayer(0)

    locations_srs = locations_lyr.GetSpatialRef()
    transform = None
    if not locations_srs.IsSame(output_srs):
        transform = osr.CoordinateTransformation(locations_srs, output_srs)
    locations = []
    for loc_feat in locations_lyr:
        loc_name = loc_feat.GetField(LOCATION_NAME_FIELD)
        loc_geom = loc_feat.GetGeometryRef()
        if transform:
            loc_geom.Transform(transform)
        locations.append((loc_name, loc_geom.GetPoint_2D(0)))

    return locations

