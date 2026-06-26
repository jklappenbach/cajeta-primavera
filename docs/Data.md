# Data access (`primavera-data`)

Multi-store data access — **SQL, DynamoDB, and Redis are first-class peers**, not
SQL with NoSQL bolted on. Deep-dive for `primavera-spec.md` §11.

## Principles

1. **Don't fake portability — access patterns *are* the data model.** A
   pretend-uniform repository that hides the store produces the worst outcomes:
   `Scan`s and hot partitions on Dynamo (`findByArbitraryField`), or a Redis layer
   that ignores the data structures that are the point. Dynamo single-table design
   (PK/SK + GSIs) and Redis structure modeling are deliberate, store-specific
   decisions. We surface them, not hide them.
2. **The borrow checker precludes *managed* ORM — that's the model's call, not a
   preference.** JPA's defining features — persistence context / identity map, lazy
   loading, dirty tracking, cascade — require the ORM to hold managed references to
   your entities and watch them mutate: a GC-shaped managed-reference graph. Under
   single ownership the ORM **can't** hold your entity — *you* own it. So entities
   are **plain owned values** and repositories are **stateless** (generate the op,
   materialize owned results, write on explicit `save`). What's left — excellent
   generated data mapping + queries — is what we build.
3. **Compile-time generated, no reflection.** Mappings and queries are generated at
   build time. For the NoSQL stores this is a genuine *advantage*: AoT-generated
   marshalling and key-condition expressions beat the reflection/builder-heavy JVM
   SDK clients, and bad access patterns are caught at compile time (§ guardrails).

## The neutral annotation union

Name annotations by their **role/function**, never by a vendor (`@DynamoDb*`) or one
store's physical structure (`@Table`/`@Column` = relational; `@Hash` = Redis). One
vocabulary spans every backend; the container name folds into `@Entity` so there's
no relational-vs-document naming fight.

| Role | Neutral annotation | SQL | DynamoDB | Redis |
|---|---|---|---|---|
| persistent type (+ container name) | `@Entity("orders")` | table | table | keyspace |
| identity — simple | `@Id` | PK | partition key | key |
| identity — placement component | `@Id(PARTITION)` | (PK) | partition key | key |
| identity — ordering component | `@Id(SORT)` | (composite PK) | sort key | (n/a) |
| stored-member name override | `@Field(name=…)` | column | attribute | hash field |
| not stored | `@Transient` | — | ignore | — |
| generated identity | `@Generated(AUTO\|UUID\|SEQUENCE\|IDENTITY)` | sequence/identity | UUID | — |
| secondary access path | `@Index(name, partition, sort, scope=GLOBAL\|LOCAL, project=…)` | index | GSI / LSI | indexed set |
| expiry | `@Ttl` | — (cleanup job) | TTL | TTL |
| optimistic concurrency | `@Version` | version col | version attr | WATCH/CAS |
| audit timestamps | `@CreatedAt` / `@UpdatedAt` | — | auto-timestamp | — |
| embedded value | `@Embedded` | flattened cols | nested map | nested |
| custom marshalling | `@Convert(by=…)` | converter | converter | converter |
| the DAO | `@Repository` | — | — | — |

`@Index` is the biggest unification: an SQL index, a Dynamo GSI/LSI, a Redis indexed
set, a Mongo index are all "an additional access path" — one annotation, with
`scope` mapping `GLOBAL`→GSI / `LOCAL`→LSI on Dynamo and ignored on SQL.

```cajeta
@Entity("orders")
class Order {
    @Id(PARTITION) String tenant;          // SQL: composite PK (tenant, id); Dynamo: PK; Redis: key prefix
    @Id(SORT)      int64  id;
    @Field("email_addr") String email;
    int64 total;
    OrderStatus status;
    @Ttl Duration retention = Duration.ofDays(30);
    @Version int64 rev;
    @Index(name="byEmail", partition="email", scope=GLOBAL) // GSI on Dynamo; index on SQL/Redis
}
```

## Repositories — generated, three query tiers

The repository interface is the only generated artifact; entities are just owned
data + mapping annotations. The store is inferred from the bound `DataSource`, and
the **available methods/annotations are store-appropriate, compile-time-enforced**.

1. **Derived methods** — parsed *at compile time* against the entity's
   fields/keys/indexes → the native op. Concise (Spring's ergonomic) without
   Spring's runtime reflection, and a bad name is a **compile error**, not a boot
   crash.
2. **`@Query`** — explicit, **store-native payload** behind a neutral name (you
   can't neutralize a query *language*, so don't). SQL string / Dynamo key-condition
   / Redis command, interpreted by the adapter.
3. **Typed builder** — over a generated metamodel (`Order.total`, `Order.status`),
   for *dynamic* (runtime-varying) queries only. Lightweight, type-safe — not the
   JPA-Criteria monster.

Results are **owned** (`#Order` / `List<#Order>`); the caller owns and drops them.
No identity map, no first-level cache (the managed-ORM features the model rules out).
**Projections** map a query to a partial DTO with its own generated mapper.

## Per-store dialects

| | SQL (Postgres/Oracle) | DynamoDB | Redis |
|---|---|---|---|
| **Key model** | `@Id` / composite `@Id(PARTITION)`+`@Id(SORT)` | `@Id(PARTITION)` + opt. `@Id(SORT)`; single-table via `@Discriminator` | `@Id` → key pattern |
| **Query** | derived + `@Query` SQL + typed builder | key access: `get(pk,sk)`, GSI/LSI queries; **`Scan` only with explicit `@Scan`** | structure-aware: hash→object; typed `@SortedSet`/`@Set`/`@Stream` |
| **Writes** | INSERT/UPDATE | PutItem, `@Condition(...)`, batch/TransactWrite | HSET, atomic ops, pipelines |
| **Consistency** | ACID | eventual (default) / strong reads; conditional | atomic ops; MULTI/EXEC |
| **`@Transactional`** | full | limited (TransactWrite, ≤ N items) | MULTI/EXEC scope |

```cajeta
@Repository interface OrderRepo {                          // dynamo (inferred from DataSource)
    Optional<Order> get(String tenant, int64 id);          // GetItem
    List<Order> byEmail(String email);                     // Query on the byEmail GSI
    @Condition("attribute_not_exists(id)") void create(Order o);
    // List<Order> findByTotal(int64 t);  ❌ compile error — would Scan; add @Scan to allow
}
```

```cajeta
@Repository interface OrderRepo {                          // redis
    Optional<Order> get(String tenant, int64 id);          // HGETALL → object
    void save(Order o);  void delete(String tenant, int64 id);
}
@SortedSet("leaderboard") interface Leaderboard {          // typed structure (not entity mapping)
    void add(String member, float64 score);  List<String> top(int32 n);
}
```

### Compile-time guardrails

The dialect is enforced at build time. The headline: on Dynamo the compiler parses
derived method names against the declared keys/indexes and **rejects anything that
would silently `Scan`** — you cannot *accidentally* table-scan; you opt in with
`@Scan`. Neither Spring Data DynamoDB nor the AWS SDK gives you that.

## Marshalling (row/item/hash ↔ owned object)

Compile-time-generated, consistent with primavera's config binder and serde codecs:
for each `@Entity`/projection the compiler emits the marshaller for the bound store's
representation — **row** (SQL), **AttributeValue map** (Dynamo), **hash/bytes**
(Redis) — from one entity declaration. No reflection, no per-row allocation beyond
the owned result. A `View<Row>` over the result buffer is available for
read-heavy/forwarding paths (zero-copy; ties to the `cajeta.io` view substrate);
default materializes an owned value.

## Transactions & consistency are NOT uniform

Held honestly: `@Transactional` and read consistency expose each store's real model
(SQL ACID; Dynamo conditional/TransactWrite + eventual-vs-strong; Redis MULTI/EXEC),
not a fake ACID veneer. A `@Transactional` on a Dynamo repo that exceeds its
transact-write limits is a compile/validation error, not a runtime surprise.

## The store-specific residue (not unioned)

A short, honestly-namespaced tail — forcing these into the union is the
ORM-over-Dynamo mistake:
- **Dynamo** — read-consistency mode, capacity mode, single-table `@Discriminator`,
  index projection type.
- **Redis** — `@SortedSet`/`@Set`/`@Stream`/pub-sub: a *different abstraction*
  (typed structure clients), not entity mapping.
- **SQL** — object-graph relations (ceded; associations are FK fields + join-into-DTO).

## Module shape

`primavera-data` core (entity model, the neutral annotation set, marshalling
codegen, the `DataSource` seam, repository generation) + per-store adapters
**`primavera-data-sql`**, **`primavera-data-dynamo`**, **`primavera-data-redis`** —
pull only the backend you use (the multi-repo / DCE choice).

## Open decisions

- **Connection/client lifecycle** — pool owned by the adapter vs. by the app; how a
  Dynamo/Redis client (long-lived, multiplexed) maps to the owned-pool model.
- **Single-table mapping depth** — how much single-table-design ergonomics
  (`@Discriminator`, polymorphic item types) to generate vs leave to `@Query`.
- **`@Scan` ergonomics** — is the explicit opt-in enough, or also a lint/cost
  warning when a `@Scan` ships?
- **Cross-store entity reuse** — may one `@Entity` bind to *two* stores (e.g. SQL of
  record + Redis cache) in one build, or is an entity store-bound?
