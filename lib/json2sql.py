# -*- coding: utf-8 -*-
"""
Created on Sat Jul  8 14:23:05 2017

@author: fnitsche

Modified for USAP-DC curator page by Neville Shane March 1 2018
"""

import os
import json
import psycopg2

config = json.loads(open('config.json', 'r').read())


def connect_to_db():
    info = config['DATABASE']
    conn = psycopg2.connect(host=info['HOST'],
                            port=info['PORT'],
                            database=info['DATABASE'],
                            user=info['USER'],
                            password=info['PASSWORD'])
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    return (conn, cur)


def parse_json(data):

    # --- checking for required fields, make sure they all have data
    fields = ["abstract", "authors", "awards", "title", "timestamp",
              "geo_e", "geo_w", "geo_n", "geo_s", "start", "stop",
              "publications", "orcid", "email"]
    # for field in fields:
    #    print(data[field])

    # --- fix some json fields
    # TODO Handle multiple authors
    data["author"] = data["authors"][0]
    (first, last) = (data["author"]["first_name"], data["author"]["last_name"])
    data["author"] = "{}, {}".format(last, first)
    print("corrected author: ", data["author"])
    if data["name"] != "":
        (first, last) = data["name"].split(' ', 1)
        data["name"] = "{}, {}".format(last, first)
        print("corrected submitter: ", data["name"])
    else:
        data["name"] = data["author"]

    # --- fix award field
    for i in range(len(data["awards"])):
        (data["awards"][i], dummy) = data["awards"][i].split(" ", 1)  # throw away the rest of the award string

    # --- should add something here to check lat lon fields

    for field in fields:
        # print(field)
        if field not in data:
            print(field)
            data[field] = ''
        else:
            print(field, " - ok")

    # print('Error reading file', in_file)
    # print('check json file for wrong EOL')

    return data


def makeBoundsGeom(north, south, east, west, cross_dateline):
    # point
    if (west == east and north == south):
        geom = "POINT(%s %s)" % (west, north)

    # polygon
    else:
        geom = "POLYGON(("
        n = 10
        if (cross_dateline):
            dlon = (-180 - west) / n
            dlat = (north - south) / n
            for i in range(n):
                geom += "%s %s," % (-180 - dlon * i, north)

            for i in range(n):
                geom += "%s %s," % (west, north - dlat * i)

            for i in range(n):
                geom += "%s %s," % (west + dlon * i, south)

            dlon = (180 - east) / n
            for i in range(n):
                geom += "%s %s," % (180 - dlon * i, south)

            for i in range(n):
                geom += "%s %s," % (east, south + dlat * i)

            for i in range(n):
                geom += "%s %s," % (east + dlon * i, north)
            # close the ring ???
            geom += "%s %s," % (-180, north)

        elif east > west:
            dlon = (west - east) / n
            dlat = (north - south) / n
            for i in range(n):
                geom += "%s %s," % (west - dlon * i, north)

            for i in range(n):
                geom += "%s %s," % (east, north - dlat * i)

            for i in range(n):
                geom += "%s %s," % (east + dlon * i, south)

            for i in range(n):
                geom += "%s %s," % (west, south + dlat * i)
            # close the ring
            geom += "%s %s," % (west, north)

        else:
            dlon = (-180 - east) / n
            dlat = (north - south) / n
            for i in range(n):
                geom += "%s %s," % (-180 - dlon * i, north)

            for i in range(n):
                geom += "%s %s," % (east, north - dlat * i)

            for i in range(n):
                geom += "%s %s," % (east + dlon * i, south)

            dlon = (180 - west) / n
            for i in range(n):
                geom += "%s %s," % (180 - dlon * i, south)

            for i in range(n):
                geom += "%s %s," % (west, south + dlat * i)

            for i in range(n):
                geom += "%s %s," % (west + dlon * i, north)
            # close the ring ???
            geom += "%s %s," % (-180, north)

        geom = geom[:-1] + "))"
    return geom


def make_sql(data, id):
    # --- prepare some parameter
    release_date = data["timestamp"][0:10]
    # print(release_date)
    url = 'http://www.usap-dc.org/dataset/usap-dc/' + id + '/' + data["timestamp"] + '/'
    # print(url)
    
    curator = "Nitsche"

    sql_out = ""
    sql_out += 'START TRANSACTION;\n\n'
    sql_out += '--NOTE: include NSF PI(s), submitter, and author(s); email+orcid optional\n'

    conn, cur = connect_to_db()

    person_ids = []
    for author in data["authors"]:
        first_name = author.get("first_name")
        last_name = author.get("last_name")
        person_id = "%s, %s" % (last_name, first_name)
        person_ids.append(person_id)

        query = "SELECT COUNT(*) FROM person WHERE id = '%s'" % person_id
        cur.execute(query)
        res = cur.fetchone()
  
        if res['count'] == 0 and person_id != "":
            if author == data["author"]:
                line = "insert into person(id,first_name, last_name, email,id_orcid) values ('{}','{}','{}',{}','{}');\n".format(person_id, first_name, last_name, data["email"], data["orcid"])
            else:
                line = "insert into person(id,first_name, last_name) values ('{}','{}','{}');\n".format(person_id, first_name, last_name)

            sql_out += line

    if data["name"] not in person_ids and data["name"] != '':
        query = "SELECT COUNT(*) FROM person WHERE id = '%s'" % data["name"]
        cur.execute(query)
        res = cur.fetchone()
        print(res)
        if res['count'] == 0:
            line = "insert into person(id,email,id_orcid) values ('{}','{}','{}');\n".format(data["name"], data["email"], data["orcid"])
            sql_out += line
    
    sql_out += '\n--NOTE: submitter_id = JSON "name"\n'
    sql_out += '--NOTE: creator = JSON "author"\n'
    sql_out += '--NOTE: url suffix = JSON "timestamp"\n'
    sql_line = """INSERT into dataset (id,doi,title,submitter_id,creator,release_date,abstract,version,url,superset,language_id,status_id,url_extra,review_status)
    VALUES ('{}','{}','{}','{}','{}','{}','{}','{}','{}','{}','{}','{}','{}','In Work');\n"""\
                    .format(id,\
                      '10.15784/'+id, \
                      data["title"], \
                      data["name"], \
                      '; '.join(person_ids), \
                      release_date, \
                      data["abstract"], \
                      '1', \
                      url, \
                      'usap-dc', \
                      'English', \
                      'Complete', \
                      '/doc/'+id+'/README_'+id+'.txt', \
                      'In Work')
    sql_out += sql_line


    sql_out += '\n--NOTE: same set of persons from above (check name and spelling)\n'
    for person_id in person_ids:
            line = "insert into  dataset_person_map(dataset_id,person_id) values ('%s','%s');\n" % \
                                   (id, person_id)
            sql_out += line

    if data["name"] not in person_ids and data["name"] != '':
        line = "insert into  dataset_person_map(dataset_id,person_id) values ('%s','%s');\n" % \
                               (id, data["name"])
        sql_out += line
  
    sql_out += '\n--NOTE: AWARDS functions:\n'
    for award in data['awards']:
        query = "SELECT COUNT(*) FROM dif WHERE dif_id = 'USAP-%s'" % award
        cur.execute(query)
        res = cur.fetchone()
        if res['count'] == 0:
            sql_out += '\n--NOTE: DIF may already exist if a previous Dataset has been submitted\n'
            line = "insert into dif(dif_id) values ('%s');\n" % \
                ('USAP-' + award)
            sql_out += line

        line = "insert into dataset_dif_map(dataset_id,dif_id) values ('%s','%s');\n" % \
            (id, 'USAP-' + award)
        sql_out += line


        sql_out += '\n--NOTE: check the award #\n'
        line = "insert into dataset_award_map(dataset_id,award_id) values ('%s','%s');\n" % \
                           (id, award)
        sql_out += line

        # look up award to see if already mapped to a program
        query = "SELECT program_id FROM award_program_map WHERE award_id = '%s';" % award
        cur.execute(query)
        res = cur.fetchone()
  
        if res is None:
            sql_out += "\n--NOTE: Need to map award to a program."
            sql_out += "\n--NOTE: look up at https://www.nsf.gov/awardsearch/showAward?AWD_ID={}\n".format(award)
            sql_out += "--insert into award_program_map(award_id,program_id) values ('{}','Antarctic Earth Sciences');\n".format(award)
            sql_out += "--insert into award_program_map(award_id,program_id) values ('{}','Antarctic Glaciology');\n".format(award)
            sql_out += "--insert into award_program_map(award_id,program_id) values ('{}','Antarctic Organisms and Ecosystems');\n".format(award)
            sql_out += "--insert into award_program_map(award_id,program_id) values ('{}','Antarctic Integrated System Science');\n".format(award)
            sql_out += "--insert into award_program_map(award_id,program_id) values ('{}','Antarctic Astrophysics and Geospace Sciences');\n".format(award)
            sql_out += "--insert into award_program_map(award_id,program_id) values ('{}','Antarctic Ocean and Atmospheric Sciences');\n\n".format(award)

            sql_out += "insert into dataset_program_map(dataset_id,program_id) values ('{}','Antarctic Ocean and Atmospheric Sciences');\n\n".format(id)
        else:
            sql_out += "insert into dataset_program_map(dataset_id,program_id) values ('{}','{}');\n\n".format(id, res['program_id'])
            if res['program_id'] == 'Antarctic Glaciology':
                curator = 'Bauer'

    sql_out += "--NOTE: reviewer is Bauer for Glaciology-funded dataset, else Nitsche\n"
    sql_out += "update dataset set review_person='{}' where id='{}';\n".format(curator,id)

    sql_out += "\n--NOTE: spatial and temp map, check coordinates\n"
    line = "insert into dataset_spatial_map(dataset_id,west,east,south,north,cross_dateline) values  ('%s','%s','%s','%s','%s','%s');\n" % \
                           (id, data["geo_w"],data["geo_e"],data["geo_s"],data["geo_n"],data["cross_dateline"])
    sql_out += line
    if data["start"] != "" or data["stop"] != "":
        line = "insert into dataset_temporal_map(dataset_id,start_date,stop_date) values ('%s','%s','%s');\n\n" % \
                               (id, data["start"], data["stop"])
        sql_out += line

    if (data["geo_w"] != '' and data["geo_e"] != '' and data["geo_s"] != '' and data["geo_n"] != '' and data["cross_dateline"] != ''):
        west = float(data["geo_w"])
        east = float(data["geo_e"])
        south = float(data["geo_s"])
        north = float(data["geo_n"])
        mid_point_lat = (south - north) / 2 + north
        mid_point_long = (east - west) / 2 + west

        geometry = "ST_GeomFromText('POINT(%s %s)', 4326)" % (mid_point_long, mid_point_lat)
        bounds_geometry = "ST_GeomFromText('%s', 4326)" % makeBoundsGeom(north, south, east, west, data["cross_dateline"])

        sql_out += "\n--NOTE: need to update geometry; need to add mid x and y\n"
        line = "update dataset_spatial_map set (geometry, bounds_geometry) = ({}, {}) WHERE dataset_id = '{}';\n\n"\
                   .format(geometry, bounds_geometry, id)
        sql_out += line

    sql_out += "--NOTE: optional; every dataset does NOT belong to an initiative\n"
    sql_out += "--insert into initiative(id) values ('WAIS Divide Ice Core');\n"
    line = "--insert into dataset_initiative_map(dataset_id,initiative_id) values ('{}','{}');\n\n".format(id,'WAIS Divide Ice Core')
    sql_out += line

    sql_out += "\n--NOTE: reference format is free text; insert CRs for multiple references\n"

    for publication in data["publications"]:
        if publication.get('doi') and publication['doi'] != "":
            line = "insert into dataset_reference_map(dataset_id,reference,doi) values ('%s','%s','%s');\n" % \
                (id, publication.get('text'), publication.get('doi'))
        else:
            line = "insert into dataset_reference_map(dataset_id,reference) values ('%s','%s');\n" % \
                (id, publication.get('text'))
        sql_out += line

    sql_out += "--NOTE: add keywords\n"
    sql_out += "INSERT into dataset_keyword_map(dataset_id,  keyword_id) values ('{}','ik-0001'); -- Antarctica\n".format(id)
    sql_out += "INSERT into dataset_keyword_map(dataset_id,  keyword_id) values ('{}','ik-0052'); -- Cryosphere\n".format(id)
    sql_out += "INSERT into dataset_keyword_map(dataset_id,  keyword_id) values ('{}','ik-0009'); -- Glaciers and Ice sheets\n".format(id)
    sql_out += "INSERT into dataset_keyword_map(dataset_id,  keyword_id) values ('{}','ik-0067'); -- Snow Ice\n".format(id)
    sql_out += "INSERT into dataset_keyword_map(dataset_id,  keyword_id) values ('{}','ik-0031'); -- Glaciology\n".format(id)
    sql_out += "--INSERT into dataset_keyword_map(dataset_id,  keyword_id) values ('{}','ik-0032'); -- Ice Core Records\n".format(id)

    # user keywords
    if data["user_keywords"] != "":
        sql_out += "--NOTE: add user keywords\n"
        for keyword in data["user_keywords"].split(','):
            keyword = keyword.strip()
            # first check if the keyword is already in the database - check keyword_usap and keyword_ieda tables
            query = "SELECT keyword_id FROM keyword_ieda WHERE UPPER(keyword_label) = UPPER('%s') UNION SELECT keyword_id FROM keyword_usap WHERE UPPER(keyword_label) = UPPER('%s')" % (keyword, keyword)
            cur.execute(query)
            res = cur.fetchone()
            if res is not None:
                sql_out += "INSERT INTO dataset_keyword_map(dataset_id,  keyword_id) VALUES ('{}','{}'); -- {}\n".format(id, res['keyword_id'], keyword)
            else:
                #if not found, add to keyword_usap
                # first work out the last keyword_id used
                query = "SELECT keyword_id FROM keyword_usap ORDER BY keyword_id DESC"
                cur.execute(query)
                res = cur.fetchone()
                last_id = res['keyword_id'].replace('uk-', '')
                next_id = int(last_id) + 1
                sql_out += "--INSERT INTO keyword_usap (keyword_id, keyword_label, keyword_type_id, source) VALUES ('uk-%s', '%s', 'REPLACE_ME', 'user');\n" % \
                    (next_id, keyword)
                sql_out += "--INSERT INTO dataset_keyword_map(dataset_id,  keyword_id) VALUES ('{}','uk-{}');\n".format(id, next_id)

    sql_out += '\nCOMMIT;\n'

    return sql_out


def write_readme(data, id):
    doc_dir = os.path.join("doc", id)
    if not os.path.exists(doc_dir):
        oldmask = os.umask(000)
        os.makedirs(doc_dir, 0o775)
        os.umask(oldmask)

    out_filename = os.path.join(doc_dir, 'README_' + id + '.txt')
    text = []
    text.append('USAP-DC Dataset# ' + id + '\n')
    text.append(data["timestamp"][:10]+'\n')
    text.append('http://doi.org/10.15784/' + id+'\n')
    text.append('\nabstract:\n')
    text.append(data["abstract"]+'\n')
    text.append('\nInstruments and devices:\n')
    text.append(data["devices"]+'\n')
    text.append('\nAcquisition procedures:\n')
    text.append(data["procedures"]+'\n')
    text.append('\nContent and processing steps:\n')
    text.append(data["content"]+'\n\n')
    text.append(data["data_processing"]+'\n')
    text.append('\nLimitations and issues:\n')
    text.append(data["issues"]+'\n')
    text.append('\nCheckboxes:\n')
    text.append('* All the data are referenced in time and space.\n')
    text.append('* The data column, properties, and attributes listed/used in the data files are explained either in the description and/or the data files themselves.\n')
    text.append('* Graphs and maps (if provided) have legends.\n')
    
    
    #--- write the text to output file
    with open(out_filename,'w') as out_file:
        out_file.writelines(text)
    os.chmod(out_filename, 0o664)
    
    return out_filename


def json2sql(data, id):

    data = parse_json(data)

    if data:
        sql = make_sql(data, id)
        readme_file = write_readme(data, id)
        return sql, readme_file
    else:
        print('Error: no data have been processed!')
    return None
