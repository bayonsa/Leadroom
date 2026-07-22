local businesses = osm2pgsql.define_table({
    name = 'leadroom_osm_businesses',
    ids = { type = 'any', id_column = 'osm_id', type_column = 'osm_type' },
    columns = {
        { column = 'name', type = 'text', not_null = true },
        { column = 'category', type = 'text', not_null = true },
        { column = 'category_value', type = 'text', not_null = true },
        { column = 'website', type = 'text', not_null = true },
        { column = 'phone', type = 'text', not_null = true },
        { column = 'email', type = 'text', not_null = true },
        { column = 'address', type = 'text', not_null = true },
        { column = 'city', type = 'text', not_null = true },
        { column = 'postcode', type = 'text', not_null = true },
        { column = 'search_text', type = 'text', not_null = true },
        { column = 'location_text', type = 'text', not_null = true },
        { column = 'tags', type = 'jsonb' },
        { column = 'geom', type = 'point', projection = 4326, not_null = true },
    }
})

local places = osm2pgsql.define_table({
    name = 'leadroom_osm_places',
    ids = { type = 'relation', id_column = 'osm_id' },
    columns = {
        { column = 'name', type = 'text', not_null = true },
        { column = 'place_type', type = 'text', not_null = true },
        { column = 'admin_level', type = 'text', not_null = true },
        { column = 'search_text', type = 'text', not_null = true },
        { column = 'geom', type = 'multipolygon', projection = 4326, not_null = true },
    }
})

local category_keys = { 'amenity', 'shop', 'office', 'craft', 'tourism', 'healthcare', 'leisure' }
local ignored = {
    bench=true, bicycle_parking=true, parking=true, waste_basket=true, post_box=true,
    drinking_water=true, public_bookcase=true, recycling=true, telephone=true,
}

local function first(tags, keys)
    for _, key in ipairs(keys) do
        if tags[key] and tags[key] ~= '' then return tags[key] end
    end
    return ''
end

local function category(tags)
    for _, key in ipairs(category_keys) do
        local value = tags[key]
        if value and value ~= '' and not ignored[value] then return key, value end
    end
    return nil, nil
end

local function row(object, geom)
    local tags = object.tags
    local key, value = category(tags)
    if not key or not tags.name or tags.name == '' then return nil end
    local street = first(tags, { 'addr:street', 'contact:street' })
    local number = first(tags, { 'addr:housenumber', 'contact:housenumber' })
    local city = first(tags, { 'addr:city', 'addr:town', 'addr:village', 'contact:city' })
    local postcode = first(tags, { 'addr:postcode', 'contact:postcode' })
    local address = first(tags, { 'addr:full', 'contact:address' })
    if address == '' then address = (number .. ' ' .. street):gsub('^%s+', ''):gsub('%s+$', '') end
    local website = first(tags, { 'website', 'contact:website', 'url' })
    local phone = first(tags, { 'contact:phone', 'phone', 'contact:mobile', 'mobile' })
    local email = first(tags, { 'contact:email', 'email' })
    return {
        name = tags.name,
        category = key,
        category_value = value,
        website = website,
        phone = phone,
        email = email,
        address = address,
        city = city,
        postcode = postcode,
        search_text = string.lower(tags.name .. ' ' .. key .. ' ' .. value),
        location_text = string.lower(address .. ' ' .. city .. ' ' .. postcode),
        tags = tags,
        geom = geom,
    }
end

function osm2pgsql.process_node(object)
    local data = row(object, object:as_point())
    if data then businesses:insert(data) end
end

function osm2pgsql.process_way(object)
    if not object.is_closed then return end
    local data = row(object, object:as_polygon():centroid())
    if data then businesses:insert(data) end
end

function osm2pgsql.process_relation(object)
    if object.tags.type ~= 'multipolygon' and object.tags.type ~= 'boundary' then return end
    if object.tags.boundary == 'administrative' and object.tags.name then
        places:insert({
            name = object.tags.name,
            place_type = object.tags.place or object.tags.boundary or '',
            admin_level = object.tags.admin_level or '',
            search_text = string.lower(object.tags.name .. ' ' .. (object.tags['name:en'] or '')),
            geom = object:as_multipolygon(),
        })
    end
    local data = row(object, object:as_multipolygon():centroid())
    if data then businesses:insert(data) end
end
