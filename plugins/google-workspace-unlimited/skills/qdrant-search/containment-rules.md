# Containment Rules for qdrant_client.models

This document describes which components can contain which.

## Parent → Children Relationships

| Parent | Symbol | Children |
|--------|--------|----------|
| AbortTransferOperation | `A_0` | `α`=AbortShardTransfer |
| AppBuildTelemetry | `ă` | `A_2`=AppFeaturesTelemetry, `F_0`=FeatureFlags, `ɦ`=HnswGlobalConfig, `R_13`=RunningEnvironmentTelemetry |
| BinaryQuantization | `B_0` | `B_1`=BinaryQuantizationConfig |
| BinaryQuantizationConfig | `B_1` | `B_2`=BinaryQuantizationEncoding, `B_3`=BinaryQuantizationQueryEncoding |
| Bm25Config | `Ƀ` | `S_3`=SnowballParams, `ƭ`=TokenizerType |
| BoolIndexParams | `ɓ` | `ℬ`=BoolIndexType |
| ClusterConfigTelemetry | `C_17` | `C_30`=ConsensusConfigTelemetry, `P_8`=P2pConfigTelemetry |
| ClusterStatusOneOf1 | `C_16` | `ɾ`=RaftInfo |
| ClusterStatusTelemetry | `C_19` | `ş`=StateRole |
| ClusterTelemetry | `C_3` | `C_17`=ClusterConfigTelemetry, `C_19`=ClusterStatusTelemetry |
| CollectionClusterInfo | `C_12` | `λ`=LocalShardInfo, `R_6`=RemoteShardInfo, `R_1`=ReshardingInfo, `S_16`=ShardTransferInfo |
| CollectionConfig | `C_1` | `C_4`=CollectionParams, `Ħ`=HnswConfig, `O_0`=OptimizersConfig, `S_49`=StrictModeConfigOutput, `ʍ`=WalConfig |
| CollectionConfigTelemetry | `C_9` | `C_4`=CollectionParams, `Ħ`=HnswConfig, `O_0`=OptimizersConfig, `S_49`=StrictModeConfigOutput, `ü`=UUID, +1 more |
| CollectionInfo | `◘` | `C_1`=CollectionConfig, `C_5`=CollectionStatus, `C_11`=CollectionWarning, `U_4`=UpdateQueueInfo |
| CollectionParams | `C_4` | `S_7`=ShardingMethod |
| CollectionTelemetry | `C_10` | `C_9`=CollectionConfigTelemetry, `R_11`=ReplicaSetTelemetry, `R_1`=ReshardingInfo, `S_16`=ShardTransferInfo |
| CollectionsAggregatedTelemetry | `C_22` | `C_4`=CollectionParams |
| CollectionsAliasesResponse | `C_21` | `ą`=AliasDescription |
| CollectionsResponse | `C_15` | `C_27`=CollectionDescription |
| CollectionsTelemetry | `C_20` | `C_29`=CollectionSnapshotTelemetry |
| CountRequest | `ç` | `ƒ`=Filter |
| CreateAliasOperation | `C_23` | `ℂ`=CreateAlias |
| CreateCollection | `C_2` | `η`=HnswConfigDiff, `O_7`=OptimizersConfigDiff, `S_7`=ShardingMethod, `S_14`=StrictModeConfig, `ẃ`=WalConfigDiff |
| CreateShardingKey | `C_8` | `R_0`=ReplicaState |
| CreateShardingKeyOperation | `C_24` | `C_8`=CreateShardingKey |
| DatetimeIndexParams | `D_12` | `D_9`=DatetimeIndexType |
| DeleteAliasOperation | `D_18` | `►`=DeleteAlias |
| DeletePayload | `D_0` | `ƒ`=Filter |
| DeletePayloadOperation | `D_19` | `D_0`=DeletePayload |
| DeleteVectors | `D_1` | `ƒ`=Filter |
| DeleteVectorsOperation | `D_20` | `D_1`=DeleteVectors |
| DiscoverQuery | `D_2` | `D_6`=DiscoverInput |
| DiscoverRequest | `D_4` | `C_14`=ContextExamplePair, `ƒ`=Filter, `ɭ`=LookupLocation, `♦`=SearchParams |
| DiscoverRequestBatch | `D_21` | `D_4`=DiscoverRequest |
| DistributedCollectionTelemetry | `D_13` | `D_16`=DistributedShardTelemetry, `R_1`=ReshardingInfo, `S_16`=ShardTransferInfo |
| DistributedPeerDetails | `D_15` | `ş`=StateRole |
| DistributedPeerInfo | `D_14` | `D_15`=DistributedPeerDetails |
| DistributedReplicaTelemetry | `D_11` | `P_12`=PartialSnapshotTelemetry, `R_0`=ReplicaState, `□`=ShardStatus |
| DistributedShardTelemetry | `D_16` | `D_11`=DistributedReplicaTelemetry |
| DistributedTelemetryData | `D_17` | `D_26`=DistributedClusterTelemetry |
| DivExpression | `D_3` | `◦`=DivParams |
| DropReplicaOperation | `D_22` | `ʀ`=Replica |
| DropShardingKeyOperation | `D_23` | `D_8`=DropShardingKey |
| ErrorResponse | `ė` | `ɛ`=ErrorResponseStatus |
| ExpDecayExpression | `ə` | `D_25`=DecayParamsExpression |
| FacetRequest | `ɟ` | `ƒ`=Filter |
| FacetResponse | `F_3` | `F_4`=FacetValueHit |
| FieldCondition | `ʄ` | `G_3`=GeoBoundingBox, `ǧ`=GeoPolygon, `ǵ`=GeoRadius, `ν`=ValuesCount |
| Filter | `ƒ` | `◆`=MinShould |
| FilterSelector | `F_6` | `ƒ`=Filter |
| FloatIndexParams | `F_8` | `F_7`=FloatIndexType |
| FusionQuery | `φ` | `ℱ`=Fusion |
| GaussDecayExpression | `G_7` | `D_25`=DecayParamsExpression |
| GeoBoundingBox | `G_3` | `ℊ`=GeoPoint |
| GeoDistance | `γ` | `G_5`=GeoDistanceParams |
| GeoDistanceParams | `G_5` | `ℊ`=GeoPoint |
| GeoIndexParams | `G_4` | `G_0`=GeoIndexType |
| GeoLineString | `G_1` | `ℊ`=GeoPoint |
| GeoPolygon | `ǧ` | `G_1`=GeoLineString |
| GeoRadius | `ǵ` | `ℊ`=GeoPoint |
| GroupsResult | `ɠ` | `þ`=PointGroup |
| IndexesOneOf1 | `ı` | `Ħ`=HnswConfig |
| InlineResponse200 | `I_3` | `S_17`=ShardKeysResponse, `ʊ`=Usage |
| InlineResponse2001 | `I_13` | `ʊ`=Usage |
| InlineResponse20010 | `I_16` | `O_2`=OptimizationsResponse, `ʊ`=Usage |
| InlineResponse20011 | `I_17` | `C_21`=CollectionsAliasesResponse, `ʊ`=Usage |
| InlineResponse20013 | `I_18` | `S_30`=SnapshotDescription, `ʊ`=Usage |
| InlineResponse20014 | `I_31` | `S_30`=SnapshotDescription |
| InlineResponse20015 | `I_19` | `ρ`=Record, `ʊ`=Usage |
| InlineResponse20016 | `I_20` | `ρ`=Record, `ʊ`=Usage |
| InlineResponse20017 | `I_21` | `ų`=UpdateResult, `ʊ`=Usage |
| InlineResponse20018 | `I_22` | `▫`=ScrollResult, `ʊ`=Usage |
| InlineResponse20019 | `I_23` | `○`=ScoredPoint, `ʊ`=Usage |
| InlineResponse2002 | `I_5` | `ŧ`=TelemetryData, `ʊ`=Usage |
| InlineResponse20020 | `I_32` | `ʊ`=Usage |
| InlineResponse20021 | `I_24` | `ɠ`=GroupsResult, `ʊ`=Usage |
| InlineResponse20022 | `I_25` | `ȼ`=CountResult, `ʊ`=Usage |
| InlineResponse20023 | `I_26` | `F_3`=FacetResponse, `ʊ`=Usage |
| InlineResponse20024 | `I_27` | `Ǫ`=QueryResponse, `ʊ`=Usage |
| InlineResponse20025 | `I_28` | `Ǫ`=QueryResponse, `ʊ`=Usage |
| InlineResponse20026 | `I_29` | `S_33`=SearchMatrixPairsResponse, `ʊ`=Usage |
| InlineResponse20027 | `I_30` | `S_38`=SearchMatrixOffsetsResponse, `ʊ`=Usage |
| InlineResponse2003 | `I_14` | `ʊ`=Usage |
| InlineResponse2004 | `I_6` | `D_17`=DistributedTelemetryData, `ʊ`=Usage |
| InlineResponse2005 | `I_7` | `C_15`=CollectionsResponse, `ʊ`=Usage |
| InlineResponse2006 | `I_8` | `◘`=CollectionInfo, `ʊ`=Usage |
| InlineResponse2007 | `I_9` | `ų`=UpdateResult, `ʊ`=Usage |
| InlineResponse2008 | `I_10` | `C_18`=CollectionExistence, `ʊ`=Usage |
| InlineResponse2009 | `I_11` | `C_12`=CollectionClusterInfo, `ʊ`=Usage |
| IntegerIndexParams | `I_15` | `I_4`=IntegerIndexType |
| IsEmptyCondition | `I_2` | `P_0`=PayloadField |
| IsNullCondition | `I_0` | `P_0`=PayloadField |
| KeywordIndexParams | `κ` | `ĸ`=KeywordIndexType |
| LinDecayExpression | `L_1` | `D_25`=DecayParamsExpression |
| LocalShardInfo | `λ` | `R_0`=ReplicaState |
| LocalShardTelemetry | `L_0` | `O_1`=OptimizerTelemetry, `S_6`=SegmentTelemetry, `□`=ShardStatus, `S_43`=ShardUpdateQueueInfo |
| MoveShard | `ℳ` | `S_29`=ShardTransferMethod |
| MoveShardOperation | `M_5` | `ℳ`=MoveShard |
| MultiVectorConfig | `M_3` | `M_7`=MultiVectorComparator |
| NaiveFeedbackStrategy | `N_2` | `N_3`=NaiveFeedbackStrategyParams |
| NamedSparseVector | `N_1` | `S_1`=SparseVector |
| NearestQuery | `ɲ` | `μ`=Mmr |
| Nested | `ŋ` | `ƒ`=Filter |
| NestedCondition | `N_0` | `ŋ`=Nested |
| Optimization | `Ω` | `O_3`=OptimizationSegmentInfo, `▪`=ProgressTree, `ü`=UUID |
| OptimizationSegmentInfo | `O_3` | `ü`=UUID |
| OptimizationsResponse | `O_2` | `Ω`=Optimization, `O_3`=OptimizationSegmentInfo, `O_6`=OptimizationsSummary, `P_9`=PendingOptimization |
| OptimizerTelemetry | `O_1` | `O_5`=OperationDurationStatistics, `T_0`=TrackerTelemetry |
| OrderBy | `ø` | `•`=Direction |
| OverwritePayloadOperation | `O_4` | `ș`=SetPayload |
| PayloadIndexInfo | `P_6` | `P_7`=PayloadSchemaType |
| PendingOptimization | `P_9` | `O_3`=OptimizationSegmentInfo |
| PointGroup | `þ` | `ρ`=Record, `○`=ScoredPoint |
| PointsBatch | `★` | `ᵬ`=Batch, `ƒ`=Filter, `υ`=UpdateMode |
| PointsList | `ƥ` | `ƒ`=Filter, `▼`=PointStruct, `υ`=UpdateMode |
| PowExpression | `P_5` | `◇`=PowParams |
| Prefetch | `¶` | `ƒ`=Filter, `ɭ`=LookupLocation, `♦`=SearchParams |
| ProductQuantization | `P_10` | `P_11`=ProductQuantizationConfig |
| ProductQuantizationConfig | `P_11` | `C_6`=CompressionRatio |
| ProgressTree | `▪` | `▪`=ProgressTree |
| QueryGroupsRequest | `ǫ` | `ƒ`=Filter, `ɭ`=LookupLocation, `♦`=SearchParams |
| QueryRequest | `ʠ` | `ƒ`=Filter, `ɭ`=LookupLocation, `♦`=SearchParams |
| QueryRequestBatch | `ɋ` | `ʠ`=QueryRequest |
| QueryResponse | `Ǫ` | `○`=ScoredPoint |
| RaftInfo | `ɾ` | `ş`=StateRole |
| RecommendGroupsRequest | `R_12` | `ƒ`=Filter, `ɭ`=LookupLocation, `R_10`=RecommendStrategy, `♦`=SearchParams |
| RecommendInput | `R_2` | `R_10`=RecommendStrategy |
| RecommendQuery | `R_4` | `R_2`=RecommendInput |
| RecommendRequest | `R_5` | `ƒ`=Filter, `ɭ`=LookupLocation, `R_10`=RecommendStrategy, `♦`=SearchParams |
| RecommendRequestBatch | `R_18` | `R_5`=RecommendRequest |
| RelevanceFeedbackInput | `R_14` | `F_1`=FeedbackItem, `N_2`=NaiveFeedbackStrategy |
| RelevanceFeedbackQuery | `R_19` | `R_14`=RelevanceFeedbackInput |
| RemoteShardInfo | `R_6` | `R_0`=ReplicaState |
| RemoteShardTelemetry | `R_17` | `O_5`=OperationDurationStatistics |
| RenameAliasOperation | `R_20` | `●`=RenameAlias |
| ReplicaSetTelemetry | `R_11` | `L_0`=LocalShardTelemetry, `P_12`=PartialSnapshotTelemetry, `R_17`=RemoteShardTelemetry |
| ReplicatePoints | `R_7` | `ƒ`=Filter |
| ReplicatePointsOperation | `R_21` | `R_7`=ReplicatePoints |
| ReplicateShard | `R_3` | `S_29`=ShardTransferMethod |
| ReplicateShardOperation | `R_22` | `R_3`=ReplicateShard |
| RequestsTelemetry | `R_9` | `G_2`=GrpcTelemetry, `ŵ`=WebApiTelemetry |
| ReshardingInfo | `R_1` | `R_16`=ReshardingDirection |
| RestartTransfer | `R_8` | `S_29`=ShardTransferMethod |
| RestartTransferOperation | `R_23` | `R_8`=RestartTransfer |
| RrfQuery | `†` | `ɽ`=Rrf |
| RunningEnvironmentTelemetry | `R_13` | `©`=CpuEndian, `G_6`=GpuDeviceTelemetry |
| SampleQuery | `♥` | `§`=Sample |
| ScalarQuantization | `S_22` | `S_32`=ScalarQuantizationConfig |
| ScalarQuantizationConfig | `S_32` | `♣`=ScalarType |
| ScrollRequest | `S_2` | `ƒ`=Filter |
| ScrollResult | `▫` | `ρ`=Record |
| SearchGroupsRequest | `S_24` | `ƒ`=Filter, `♦`=SearchParams |
| SearchMatrixPairsResponse | `S_33` | `S_11`=SearchMatrixPair |
| SearchMatrixRequest | `S_25` | `ƒ`=Filter |
| SearchParams | `♦` | `Å`=AcornSearchParams, `ʔ`=QuantizationSearchParams |
| SearchRequest | `S_0` | `ƒ`=Filter, `♦`=SearchParams |
| SearchRequestBatch | `S_23` | `S_0`=SearchRequest |
| SegmentInfo | `σ` | `■`=SegmentType, `ü`=UUID |
| SegmentTelemetry | `S_6` | `P_13`=PayloadIndexTelemetry, `S_4`=SegmentConfig, `σ`=SegmentInfo, `V_1`=VectorIndexSearchesTelemetry |
| SetPayload | `ș` | `ƒ`=Filter |
| SetPayloadOperation | `S_26` | `ș`=SetPayload |
| ShardCleanStatusTelemetryOneOf1 | `S_34` | `S_40`=ShardCleanStatusProgressTelemetry |
| ShardCleanStatusTelemetryOneOf2 | `S_35` | `S_39`=ShardCleanStatusFailedTelemetry |
| ShardKeysResponse | `S_17` | `S_28`=ShardKeyDescription |
| ShardSnapshotRecover | `S_36` | `S_12`=SnapshotPriority |
| ShardTransferInfo | `S_16` | `S_29`=ShardTransferMethod |
| SnapshotRecover | `S_10` | `S_12`=SnapshotPriority |
| SnowballParams | `S_3` | `ʂ`=Snowball, `S_13`=SnowballLanguage |
| SparseIndexConfig | `S_18` | `V_2`=VectorStorageDatatype |
| SparseIndexParams | `S_19` | `Đ`=Datatype |
| SparseVectorDataConfig | `S_27` | `ɯ`=Modifier, `S_18`=SparseIndexConfig |
| SparseVectorParams | `S_20` | `ɯ`=Modifier, `S_19`=SparseIndexParams |
| StartResharding | `S_9` | `R_16`=ReshardingDirection |
| StartReshardingOperation | `S_37` | `S_9`=StartResharding |
| StopwordsSet | `◙` | `ŀ`=Language |
| TelemetryData | `ŧ` | `ă`=AppBuildTelemetry, `C_3`=ClusterTelemetry, `C_20`=CollectionsTelemetry, `H_0`=HardwareTelemetry, `M_2`=MemoryTelemetry, +1 more |
| TextIndexParams | `ʈ` | `S_3`=SnowballParams, `τ`=TextIndexType, `ƭ`=TokenizerType |
| TrackerTelemetry | `T_0` | `ü`=UUID |
| UpdateCollection | `U_2` | `C_28`=CollectionParamsDiff, `η`=HnswConfigDiff, `O_7`=OptimizersConfigDiff, `S_14`=StrictModeConfig |
| UpdateResult | `ų` | `U_0`=UpdateStatus |
| UpdateVectors | `ʉ` | `ƒ`=Filter, `P_4`=PointVectors |
| UpdateVectorsOperation | `U_7` | `ʉ`=UpdateVectors |
| Usage | `ʊ` | `ħ`=HardwareUsage, `ɪ`=InferenceUsage |
| UuidIndexParams | `U_3` | `U_1`=UuidIndexType |
| VectorDataConfig | `ỽ` | `δ`=Distance, `M_3`=MultiVectorConfig, `V_2`=VectorStorageDatatype |
| VectorIndexSearchesTelemetry | `V_1` | `O_5`=OperationDurationStatistics |
| VectorParams | `ʋ` | `Đ`=Datatype, `δ`=Distance, `η`=HnswConfigDiff, `M_3`=MultiVectorConfig |
| VectorParamsDiff | `V_0` | `η`=HnswConfigDiff |