# Redis

Redis is used for storing the tasks's Results, and their state values. 

## Key Format

All keys on Redis have the application's name as a prefix, like this:

```
{app_name}.mognet.
```

For example, a result with ID `1e6883d4-afcf-437c-9211-33d6180ae115` on an App named `mognet_demo` will be put into the following key:

```
mognet_demo.mognet.result.1e6883d4-afcf-437c-9211-33d6180ae115
```

You can use this guarantee to easily list keys corresponding to this app, using the `KEYS [pattern]` command on the `redis-cli`

```
# redis-cli
127.0.0.1:6379> keys mognet_demo.*
  1) "mognet_demo.mognet.result.f1718804-0cb9-49f0-811a-19321fe59407/value"
  2) "mognet_demo.mognet.result.84296b48-ca64-4f38-9954-bb179c5c6cd7"
  3) "mognet_demo.mognet.result.cf210e70-3f3c-4d42-992e-390013117631"
  4) "mognet_demo.mognet.result.806f4a4f-aab5-465a-a6a9-455fc87f158c/value"
  (...)
```

## Handling Memory Issues

Since Redis is a memory-based storage backend, there are some things that were done to help prevent out of memory situations.

### Result Backend

- A default TTL of 21 days is used for the Results
- A default TTL of 7 days is used for the Results's values
- GZIP compression is applied to Result values
- Result information, [Metadata](../advanced/metadata.md), and result values, are all stored separately.

You can configure these values via the [`RedisResultBackendSettings`][mognet.backend.backend_config.RedisResultBackendSettings] class's following properties:

- `result_ttl`
- `result_value_ttl`

### State Backend

- A default TTL of 7200s has been set for state values.

You can configure the value via the [`RedisStateBackendSettings`][mognet.state.state_backend_config.RedisStateBackendSettings] class's `state_ttl` property.

## Recommended configuration on Redis

We recommending setting key eviction policies to expire keys when there's memory pressure via the `maxmemory-policy` and `maxmemory` settings, see [Key eviction](https://redis.io/docs/manual/eviction/).

The Redis server, should, anyway, have plenty of memory available for the Mognet database, especially when running jobs with tens or thousands of tasks, otherwise task state may become corrupted, which will break Mognet in spectacular ways.

We also recommend setting `timeout` to a value higher than `0`, because otherwise Redis will never close connections. If you don't, and have hundreds or thousands of Mognet Workers, each dealing with more than one task each, will cause the `maxclients` limit to be reached very quickly.
