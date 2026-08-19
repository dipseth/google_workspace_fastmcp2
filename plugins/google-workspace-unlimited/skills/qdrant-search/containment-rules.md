# Containment Rules for qdrant_client.models

This document describes which components can contain which.

## Parent → Children Relationships

| Parent | Symbol | Children |
|--------|--------|----------|
| AbortTransferOperation | `A_0` | `α`=AbortShardTransfer |
| AppBuildTelemetry | `ă` | `A_2`=AppFeaturesTelemetry, `F_0`=FeatureFlags, `ɦ`=HnswGlobalConfig, `R_13`=RunningEnvironmentTelemetry, `A_2`=AppFeaturesTelemetry, +7 more |
| BinaryQuantization | `B_0` | `B_1`=BinaryQuantizationConfig |
| BinaryQuantizationConfig | `B_1` | `B_2`=BinaryQuantizationEncoding, `B_3`=BinaryQuantizationQueryEncoding, `B_2`=BinaryQuantizationEncoding, `B_3`=BinaryQuantizationQueryEncoding |
| Bm25Config | `Ƀ` | `ƭ`=TokenizerType, `S_3`=SnowballParams |
| BoolIndexParams | `ɓ` | `ℬ`=BoolIndexType |
| ClusterConfigTelemetry | `C_17` | `P_8`=P2pConfigTelemetry, `C_30`=ConsensusConfigTelemetry, `P_8`=P2pConfigTelemetry, `C_30`=ConsensusConfigTelemetry, `P_8`=P2pConfigTelemetry, +3 more |
| ClusterStatusOneOf1 | `C_16` | `ɾ`=RaftInfo |
| ClusterStatusTelemetry | `C_19` | `ş`=StateRole, `ş`=StateRole, `ş`=StateRole, `ş`=StateRole |
| ClusterTelemetry | `C_3` | `C_19`=ClusterStatusTelemetry, `C_17`=ClusterConfigTelemetry, `C_19`=ClusterStatusTelemetry, `C_17`=ClusterConfigTelemetry, `C_19`=ClusterStatusTelemetry, +1 more |
| CollectionClusterInfo | `C_12` | `λ`=LocalShardInfo, `R_6`=RemoteShardInfo, `S_16`=ShardTransferInfo, `R_1`=ReshardingInfo, `λ`=LocalShardInfo, +3 more |
| CollectionConfig | `C_1` | `C_4`=CollectionParams, `Ħ`=HnswConfig, `O_0`=OptimizersConfig, `ʍ`=WalConfig, `S_49`=StrictModeConfigOutput, +10 more |
| CollectionConfigTelemetry | `C_9` | `C_4`=CollectionParams, `Ħ`=HnswConfig, `O_0`=OptimizersConfig, `ʍ`=WalConfig, `S_49`=StrictModeConfigOutput, +7 more |
| CollectionInfo | `◘` | `C_5`=CollectionStatus, `C_11`=CollectionWarning, `C_1`=CollectionConfig, `U_4`=UpdateQueueInfo, `C_5`=CollectionStatus, +3 more |
| CollectionParams | `C_4` | `S_7`=ShardingMethod, `S_7`=ShardingMethod, `S_7`=ShardingMethod, `S_7`=ShardingMethod, `S_7`=ShardingMethod, +2 more |
| CollectionTelemetry | `C_10` | `C_9`=CollectionConfigTelemetry, `R_11`=ReplicaSetTelemetry, `S_16`=ShardTransferInfo, `R_1`=ReshardingInfo |
| CollectionsAggregatedTelemetry | `C_22` | `C_4`=CollectionParams |
| CollectionsAliasesResponse | `C_21` | `ą`=AliasDescription, `ą`=AliasDescription |
| CollectionsResponse | `C_15` | `C_27`=CollectionDescription, `C_27`=CollectionDescription |
| CollectionsTelemetry | `C_20` | `C_29`=CollectionSnapshotTelemetry, `C_29`=CollectionSnapshotTelemetry, `C_29`=CollectionSnapshotTelemetry |
| CountRequest | `ç` | `ƒ`=Filter |
| CreateAliasOperation | `C_23` | `ℂ`=CreateAlias |
| CreateCollection | `C_2` | `S_7`=ShardingMethod, `η`=HnswConfigDiff, `ẃ`=WalConfigDiff, `O_7`=OptimizersConfigDiff, `S_14`=StrictModeConfig |
| CreateShardingKey | `C_8` | `R_0`=ReplicaState, `R_0`=ReplicaState |
| CreateShardingKeyOperation | `C_24` | `C_8`=CreateShardingKey |
| DatetimeIndexParams | `D_12` | `D_9`=DatetimeIndexType |
| DeleteAliasOperation | `D_18` | `►`=DeleteAlias |
| DeletePayload | `D_0` | `ƒ`=Filter, `ƒ`=Filter |
| DeletePayloadOperation | `D_19` | `D_0`=DeletePayload |
| DeleteVectors | `D_1` | `ƒ`=Filter, `ƒ`=Filter |
| DeleteVectorsOperation | `D_20` | `D_1`=DeleteVectors |
| DiscoverQuery | `D_2` | `D_6`=DiscoverInput |
| DiscoverRequest | `D_4` | `C_14`=ContextExamplePair, `ƒ`=Filter, `♦`=SearchParams, `ɭ`=LookupLocation, `C_14`=ContextExamplePair, +3 more |
| DiscoverRequestBatch | `D_21` | `D_4`=DiscoverRequest |
| DistributedCollectionTelemetry | `D_13` | `D_16`=DistributedShardTelemetry, `R_1`=ReshardingInfo, `S_16`=ShardTransferInfo |
| DistributedPeerDetails | `D_15` | `ş`=StateRole, `ş`=StateRole |
| DistributedPeerInfo | `D_14` | `D_15`=DistributedPeerDetails |
| DistributedReplicaTelemetry | `D_11` | `R_0`=ReplicaState, `□`=ShardStatus, `P_12`=PartialSnapshotTelemetry, `R_0`=ReplicaState, `□`=ShardStatus, +4 more |
| DistributedShardTelemetry | `D_16` | `D_11`=DistributedReplicaTelemetry, `D_11`=DistributedReplicaTelemetry |
| DistributedTelemetryData | `D_17` | `D_26`=DistributedClusterTelemetry, `D_26`=DistributedClusterTelemetry |
| DivExpression | `D_3` | `◦`=DivParams |
| DropReplicaOperation | `D_22` | `ʀ`=Replica |
| DropShardingKeyOperation | `D_23` | `D_8`=DropShardingKey |
| ErrorResponse | `ė` | `ɛ`=ErrorResponseStatus |
| ExpDecayExpression | `ə` | `D_25`=DecayParamsExpression |
| FacetRequest | `ɟ` | `ƒ`=Filter |
| FacetResponse | `F_3` | `F_4`=FacetValueHit, `F_4`=FacetValueHit |
| FieldCondition | `ʄ` | `G_3`=GeoBoundingBox, `ǵ`=GeoRadius, `ǧ`=GeoPolygon, `ν`=ValuesCount |
| Filter | `ƒ` | `◆`=MinShould, `◆`=MinShould, `◆`=MinShould, `◆`=MinShould, `◆`=MinShould, +28 more |
| FilterSelector | `F_6` | `ƒ`=Filter |
| FloatIndexParams | `F_8` | `F_7`=FloatIndexType |
| FusionQuery | `φ` | `ℱ`=Fusion |
| GaussDecayExpression | `G_7` | `D_25`=DecayParamsExpression |
| GeoBoundingBox | `G_3` | `ℊ`=GeoPoint, `ℊ`=GeoPoint, `ℊ`=GeoPoint, `ℊ`=GeoPoint |
| GeoDistance | `γ` | `G_5`=GeoDistanceParams |
| GeoDistanceParams | `G_5` | `ℊ`=GeoPoint, `ℊ`=GeoPoint |
| GeoIndexParams | `G_4` | `G_0`=GeoIndexType |
| GeoLineString | `G_1` | `ℊ`=GeoPoint, `ℊ`=GeoPoint, `ℊ`=GeoPoint, `ℊ`=GeoPoint, `ℊ`=GeoPoint |
| GeoPolygon | `ǧ` | `G_1`=GeoLineString, `G_1`=GeoLineString, `G_1`=GeoLineString, `G_1`=GeoLineString |
| GeoRadius | `ǵ` | `ℊ`=GeoPoint, `ℊ`=GeoPoint |
| GroupsResult | `ɠ` | `þ`=PointGroup, `þ`=PointGroup |
| IndexesOneOf1 | `ı` | `Ħ`=HnswConfig |
| InlineResponse200 | `I_3` | `ʊ`=Usage, `S_17`=ShardKeysResponse |
| InlineResponse2001 | `I_13` | `ʊ`=Usage |
| InlineResponse20010 | `I_16` | `ʊ`=Usage, `O_2`=OptimizationsResponse |
| InlineResponse20011 | `I_17` | `ʊ`=Usage, `C_21`=CollectionsAliasesResponse |
| InlineResponse20013 | `I_18` | `ʊ`=Usage, `S_30`=SnapshotDescription |
| InlineResponse20014 | `I_31` | `S_30`=SnapshotDescription |
| InlineResponse20015 | `I_19` | `ʊ`=Usage, `ρ`=Record |
| InlineResponse20016 | `I_20` | `ʊ`=Usage, `ρ`=Record |
| InlineResponse20017 | `I_21` | `ʊ`=Usage, `ų`=UpdateResult |
| InlineResponse20018 | `I_22` | `ʊ`=Usage, `▫`=ScrollResult |
| InlineResponse20019 | `I_23` | `ʊ`=Usage, `○`=ScoredPoint |
| InlineResponse2002 | `I_5` | `ʊ`=Usage, `ŧ`=TelemetryData |
| InlineResponse20020 | `I_32` | `ʊ`=Usage |
| InlineResponse20021 | `I_24` | `ʊ`=Usage, `ɠ`=GroupsResult |
| InlineResponse20022 | `I_25` | `ʊ`=Usage, `ȼ`=CountResult |
| InlineResponse20023 | `I_26` | `ʊ`=Usage, `F_3`=FacetResponse |
| InlineResponse20024 | `I_27` | `ʊ`=Usage, `Ǫ`=QueryResponse |
| InlineResponse20025 | `I_28` | `ʊ`=Usage, `Ǫ`=QueryResponse |
| InlineResponse20026 | `I_29` | `ʊ`=Usage, `S_33`=SearchMatrixPairsResponse |
| InlineResponse20027 | `I_30` | `ʊ`=Usage, `S_38`=SearchMatrixOffsetsResponse |
| InlineResponse2003 | `I_14` | `ʊ`=Usage |
| InlineResponse2004 | `I_6` | `ʊ`=Usage, `D_17`=DistributedTelemetryData |
| InlineResponse2005 | `I_7` | `ʊ`=Usage, `C_15`=CollectionsResponse |
| InlineResponse2006 | `I_8` | `ʊ`=Usage, `◘`=CollectionInfo |
| InlineResponse2007 | `I_9` | `ʊ`=Usage, `ų`=UpdateResult |
| InlineResponse2008 | `I_10` | `ʊ`=Usage, `C_18`=CollectionExistence |
| InlineResponse2009 | `I_11` | `ʊ`=Usage, `C_12`=CollectionClusterInfo |
| IntegerIndexParams | `I_15` | `I_4`=IntegerIndexType |
| IsEmptyCondition | `I_2` | `P_0`=PayloadField |
| IsNullCondition | `I_0` | `P_0`=PayloadField |
| KeywordIndexParams | `κ` | `ĸ`=KeywordIndexType |
| LinDecayExpression | `L_1` | `D_25`=DecayParamsExpression |
| LocalShardInfo | `λ` | `R_0`=ReplicaState, `R_0`=ReplicaState, `R_0`=ReplicaState |
| LocalShardTelemetry | `L_0` | `□`=ShardStatus, `S_6`=SegmentTelemetry, `O_1`=OptimizerTelemetry, `S_43`=ShardUpdateQueueInfo, `□`=ShardStatus, +7 more |
| MoveShard | `ℳ` | `S_29`=ShardTransferMethod, `S_29`=ShardTransferMethod |
| MoveShardOperation | `M_5` | `ℳ`=MoveShard |
| MultiVectorConfig | `M_3` | `M_7`=MultiVectorComparator, `M_7`=MultiVectorComparator, `M_7`=MultiVectorComparator |
| NaiveFeedbackStrategy | `N_2` | `N_3`=NaiveFeedbackStrategyParams, `N_3`=NaiveFeedbackStrategyParams, `N_3`=NaiveFeedbackStrategyParams, `N_3`=NaiveFeedbackStrategyParams |
| NamedSparseVector | `N_1` | `S_1`=SparseVector |
| NearestQuery | `ɲ` | `μ`=Mmr |
| Nested | `ŋ` | `ƒ`=Filter, `ƒ`=Filter |
| NestedCondition | `N_0` | `ŋ`=Nested |
| Optimization | `Ω` | `ü`=UUID, `O_3`=OptimizationSegmentInfo, `▪`=ProgressTree, `ü`=UUID, `O_3`=OptimizationSegmentInfo, +10 more |
| OptimizationSegmentInfo | `O_3` | `ü`=UUID, `ü`=UUID, `ü`=UUID, `ü`=UUID, `ü`=UUID, +6 more |
| OptimizationsResponse | `O_2` | `O_6`=OptimizationsSummary, `Ω`=Optimization, `P_9`=PendingOptimization, `Ω`=Optimization, `O_3`=OptimizationSegmentInfo, +5 more |
| OptimizerTelemetry | `O_1` | `O_5`=OperationDurationStatistics, `T_0`=TrackerTelemetry, `O_5`=OperationDurationStatistics, `T_0`=TrackerTelemetry, `O_5`=OperationDurationStatistics, +3 more |
| OrderBy | `ø` | `•`=Direction |
| OverwritePayloadOperation | `O_4` | `ș`=SetPayload |
| PayloadIndexInfo | `P_6` | `P_7`=PayloadSchemaType |
| PendingOptimization | `P_9` | `O_3`=OptimizationSegmentInfo, `O_3`=OptimizationSegmentInfo, `O_3`=OptimizationSegmentInfo |
| PointGroup | `þ` | `○`=ScoredPoint, `ρ`=Record, `○`=ScoredPoint, `ρ`=Record, `○`=ScoredPoint, +1 more |
| PointsBatch | `★` | `ᵬ`=Batch, `ƒ`=Filter, `υ`=UpdateMode |
| PointsList | `ƥ` | `▼`=PointStruct, `ƒ`=Filter, `υ`=UpdateMode |
| PowExpression | `P_5` | `◇`=PowParams |
| Prefetch | `¶` | `ƒ`=Filter, `♦`=SearchParams, `ɭ`=LookupLocation |
| ProductQuantization | `P_10` | `P_11`=ProductQuantizationConfig |
| ProductQuantizationConfig | `P_11` | `C_6`=CompressionRatio, `C_6`=CompressionRatio |
| ProgressTree | `▪` | `▪`=ProgressTree, `▪`=ProgressTree, `▪`=ProgressTree, `▪`=ProgressTree, `▪`=ProgressTree, +1 more |
| QueryGroupsRequest | `ǫ` | `ƒ`=Filter, `♦`=SearchParams, `ɭ`=LookupLocation |
| QueryRequest | `ʠ` | `ƒ`=Filter, `♦`=SearchParams, `ɭ`=LookupLocation, `ƒ`=Filter, `♦`=SearchParams, +1 more |
| QueryRequestBatch | `ɋ` | `ʠ`=QueryRequest |
| QueryResponse | `Ǫ` | `○`=ScoredPoint, `○`=ScoredPoint |
| RaftInfo | `ɾ` | `ş`=StateRole, `ş`=StateRole |
| RecommendGroupsRequest | `R_12` | `R_10`=RecommendStrategy, `ƒ`=Filter, `♦`=SearchParams, `ɭ`=LookupLocation |
| RecommendInput | `R_2` | `R_10`=RecommendStrategy, `R_10`=RecommendStrategy |
| RecommendQuery | `R_4` | `R_2`=RecommendInput |
| RecommendRequest | `R_5` | `R_10`=RecommendStrategy, `ƒ`=Filter, `♦`=SearchParams, `ɭ`=LookupLocation, `R_10`=RecommendStrategy, +3 more |
| RecommendRequestBatch | `R_18` | `R_5`=RecommendRequest |
| RelevanceFeedbackInput | `R_14` | `F_1`=FeedbackItem, `N_2`=NaiveFeedbackStrategy, `F_1`=FeedbackItem, `N_2`=NaiveFeedbackStrategy |
| RelevanceFeedbackQuery | `R_19` | `R_14`=RelevanceFeedbackInput |
| RemoteShardInfo | `R_6` | `R_0`=ReplicaState, `R_0`=ReplicaState, `R_0`=ReplicaState |
| RemoteShardTelemetry | `R_17` | `O_5`=OperationDurationStatistics, `O_5`=OperationDurationStatistics, `O_5`=OperationDurationStatistics, `O_5`=OperationDurationStatistics, `O_5`=OperationDurationStatistics, +1 more |
| RenameAliasOperation | `R_20` | `●`=RenameAlias |
| ReplicaSetTelemetry | `R_11` | `L_0`=LocalShardTelemetry, `R_17`=RemoteShardTelemetry, `P_12`=PartialSnapshotTelemetry, `L_0`=LocalShardTelemetry, `R_17`=RemoteShardTelemetry, +1 more |
| ReplicatePoints | `R_7` | `ƒ`=Filter, `ƒ`=Filter |
| ReplicatePointsOperation | `R_21` | `R_7`=ReplicatePoints |
| ReplicateShard | `R_3` | `S_29`=ShardTransferMethod, `S_29`=ShardTransferMethod |
| ReplicateShardOperation | `R_22` | `R_3`=ReplicateShard |
| RequestsTelemetry | `R_9` | `ŵ`=WebApiTelemetry, `G_2`=GrpcTelemetry, `ŵ`=WebApiTelemetry, `G_2`=GrpcTelemetry, `ŵ`=WebApiTelemetry, +1 more |
| ReshardingInfo | `R_1` | `R_16`=ReshardingDirection, `R_16`=ReshardingDirection, `R_16`=ReshardingDirection, `R_16`=ReshardingDirection, `R_16`=ReshardingDirection |
| RestartTransfer | `R_8` | `S_29`=ShardTransferMethod, `S_29`=ShardTransferMethod |
| RestartTransferOperation | `R_23` | `R_8`=RestartTransfer |
| RrfQuery | `†` | `ɽ`=Rrf |
| RunningEnvironmentTelemetry | `R_13` | `©`=CpuEndian, `G_6`=GpuDeviceTelemetry, `©`=CpuEndian, `G_6`=GpuDeviceTelemetry, `©`=CpuEndian, +3 more |
| SampleQuery | `♥` | `§`=Sample |
| ScalarQuantization | `S_22` | `S_32`=ScalarQuantizationConfig |
| ScalarQuantizationConfig | `S_32` | `♣`=ScalarType, `♣`=ScalarType |
| ScrollRequest | `S_2` | `ƒ`=Filter |
| ScrollResult | `▫` | `ρ`=Record, `ρ`=Record |
| SearchGroupsRequest | `S_24` | `ƒ`=Filter, `♦`=SearchParams |
| SearchMatrixPairsResponse | `S_33` | `S_11`=SearchMatrixPair, `S_11`=SearchMatrixPair |
| SearchMatrixRequest | `S_25` | `ƒ`=Filter |
| SearchParams | `♦` | `ʔ`=QuantizationSearchParams, `Å`=AcornSearchParams, `ʔ`=QuantizationSearchParams, `Å`=AcornSearchParams, `ʔ`=QuantizationSearchParams, +21 more |
| SearchRequest | `S_0` | `ƒ`=Filter, `♦`=SearchParams, `ƒ`=Filter, `♦`=SearchParams |
| SearchRequestBatch | `S_23` | `S_0`=SearchRequest |
| SegmentInfo | `σ` | `ü`=UUID, `■`=SegmentType, `ü`=UUID, `■`=SegmentType, `ü`=UUID, +5 more |
| SegmentTelemetry | `S_6` | `σ`=SegmentInfo, `S_4`=SegmentConfig, `V_1`=VectorIndexSearchesTelemetry, `P_13`=PayloadIndexTelemetry, `σ`=SegmentInfo, +11 more |
| SetPayload | `ș` | `ƒ`=Filter, `ƒ`=Filter, `ƒ`=Filter |
| SetPayloadOperation | `S_26` | `ș`=SetPayload |
| ShardCleanStatusTelemetryOneOf1 | `S_34` | `S_40`=ShardCleanStatusProgressTelemetry |
| ShardCleanStatusTelemetryOneOf2 | `S_35` | `S_39`=ShardCleanStatusFailedTelemetry |
| ShardKeysResponse | `S_17` | `S_28`=ShardKeyDescription, `S_28`=ShardKeyDescription |
| ShardSnapshotRecover | `S_36` | `S_12`=SnapshotPriority |
| ShardTransferInfo | `S_16` | `S_29`=ShardTransferMethod, `S_29`=ShardTransferMethod, `S_29`=ShardTransferMethod, `S_29`=ShardTransferMethod, `S_29`=ShardTransferMethod |
| SnapshotRecover | `S_10` | `S_12`=SnapshotPriority |
| SnowballParams | `S_3` | `ʂ`=Snowball, `S_13`=SnowballLanguage, `ʂ`=Snowball, `S_13`=SnowballLanguage, `ʂ`=Snowball, +3 more |
| SparseIndexConfig | `S_18` | `V_2`=VectorStorageDatatype, `V_2`=VectorStorageDatatype |
| SparseIndexParams | `S_19` | `Đ`=Datatype, `Đ`=Datatype |
| SparseVectorDataConfig | `S_27` | `S_18`=SparseIndexConfig, `ɯ`=Modifier |
| SparseVectorParams | `S_20` | `S_19`=SparseIndexParams, `ɯ`=Modifier |
| StartResharding | `S_9` | `R_16`=ReshardingDirection, `R_16`=ReshardingDirection |
| StartReshardingOperation | `S_37` | `S_9`=StartResharding |
| StopwordsSet | `◙` | `ŀ`=Language |
| TelemetryData | `ŧ` | `ă`=AppBuildTelemetry, `C_20`=CollectionsTelemetry, `C_3`=ClusterTelemetry, `R_9`=RequestsTelemetry, `M_2`=MemoryTelemetry, +7 more |
| TextIndexParams | `ʈ` | `τ`=TextIndexType, `ƭ`=TokenizerType, `S_3`=SnowballParams |
| TrackerTelemetry | `T_0` | `ü`=UUID, `ü`=UUID, `ü`=UUID, `ü`=UUID, `ü`=UUID, +5 more |
| UpdateCollection | `U_2` | `O_7`=OptimizersConfigDiff, `C_28`=CollectionParamsDiff, `η`=HnswConfigDiff, `S_14`=StrictModeConfig |
| UpdateResult | `ų` | `U_0`=UpdateStatus, `U_0`=UpdateStatus, `U_0`=UpdateStatus |
| UpdateVectors | `ʉ` | `P_4`=PointVectors, `ƒ`=Filter, `P_4`=PointVectors, `ƒ`=Filter |
| UpdateVectorsOperation | `U_7` | `ʉ`=UpdateVectors |
| Usage | `ʊ` | `ħ`=HardwareUsage, `ɪ`=InferenceUsage, `ħ`=HardwareUsage, `ɪ`=InferenceUsage, `ħ`=HardwareUsage, +49 more |
| UuidIndexParams | `U_3` | `U_1`=UuidIndexType |
| VectorDataConfig | `ỽ` | `δ`=Distance, `M_3`=MultiVectorConfig, `V_2`=VectorStorageDatatype |
| VectorIndexSearchesTelemetry | `V_1` | `O_5`=OperationDurationStatistics, `O_5`=OperationDurationStatistics, `O_5`=OperationDurationStatistics, `O_5`=OperationDurationStatistics, `O_5`=OperationDurationStatistics, +40 more |
| VectorParams | `ʋ` | `δ`=Distance, `η`=HnswConfigDiff, `Đ`=Datatype, `M_3`=MultiVectorConfig |
| VectorParamsDiff | `V_0` | `η`=HnswConfigDiff |