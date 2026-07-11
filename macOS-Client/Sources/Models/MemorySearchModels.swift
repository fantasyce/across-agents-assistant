import Foundation

enum MemorySearchScope: String, CaseIterable, Identifiable {
    case ordinary
    case pendingReview

    var id: String { rawValue }
    var requestStatus: String? { self == .pendingReview ? "pending" : nil }
    var includesPending: Bool { self == .pendingReview }
}

enum MemoryRetrievalRoute: String, CaseIterable, Codable, Identifiable {
    case keyword
    case embedding
    case evidenceGraph = "evidence_graph"
    case projectProfile = "project_profile"
    case loopRecall = "loop_recall"

    var id: String { rawValue }
}

struct MemorySearchRequest: Encodable, Equatable {
    let query: String
    let projectRoot: String?
    let mode: String
    let status: String?
    let limit: Int
}

struct MemoryMergedRetrieveRequest: Encodable, Equatable {
    let query: String
    let routes: [MemoryRetrievalRoute]
    let projectRoot: String?
    let allProjects: Bool
    let status: String?
    let reviewPending: Bool
    let limit: Int
    let includeRouteResults: Bool
}

struct MemoryImproveRequest: Encodable, Equatable {
    let projectRoot: String?
    let allProjects: Bool
    let sourceIds: [String]
    let similarityThreshold: Double
    let maxProposalLength: Int
}

struct MemoryStatusUpdateRequest: Encodable, Equatable {
    let status: String
}

struct MemorySearchResponse: Decodable, Equatable {
    let results: [AcrossMemoryEntry]
    let resultCount: Int
    let statusFilter: String?

    enum CodingKeys: String, CodingKey {
        case results
        case resultCount = "result_count"
        case statusFilter = "status_filter"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        if let direct = try? container.decode([AcrossMemoryEntry].self, forKey: .results) {
            results = direct
        } else {
            results = (try container.decodeIfPresent([MemorySearchResultEnvelope].self, forKey: .results) ?? []).map(\.entry)
        }
        resultCount = try container.decodeIfPresent(Int.self, forKey: .resultCount) ?? results.count
        statusFilter = try container.decodeIfPresent(String.self, forKey: .statusFilter)
    }
}

struct MemoryMergedRetrieveResponse: Decodable, Equatable {
    let strategy: String?
    let routes: [MemoryRetrievalRoute]
    let localOnly: Bool?
    let deterministic: Bool?
    let resultCount: Int
    let results: [MemoryMergedResult]
    let routeResults: [MemoryRouteResult]

    enum CodingKeys: String, CodingKey {
        case strategy
        case routes
        case localOnly = "local_only"
        case deterministic
        case resultCount = "result_count"
        case results
        case routeResults = "route_results"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        strategy = try container.decodeIfPresent(String.self, forKey: .strategy)
        routes = try container.decodeIfPresent([MemoryRetrievalRoute].self, forKey: .routes) ?? []
        localOnly = try container.decodeIfPresent(Bool.self, forKey: .localOnly)
        deterministic = try container.decodeIfPresent(Bool.self, forKey: .deterministic)
        results = try container.decodeIfPresent([MemoryMergedResult].self, forKey: .results) ?? []
        resultCount = try container.decodeIfPresent(Int.self, forKey: .resultCount) ?? results.count
        routeResults = try container.decodeIfPresent([MemoryRouteResult].self, forKey: .routeResults) ?? []
    }
}

struct MemoryMergedResult: Decodable, Equatable, Identifiable {
    let entry: AcrossMemoryEntry
    let reciprocalRankScore: Double?
    let matchedRouteCount: Int
    let mergedRank: Int?
    let classification: MemoryClassification?
    let routeContributions: [MemoryRouteContribution]

    var id: String { entry.id }
    var distilledProposal: MemoryDistilledPayload? { MemoryDistilledPayload.decode(from: entry.text) }

    enum CodingKeys: String, CodingKey {
        case entry
        case reciprocalRankScore = "reciprocal_rank_score"
        case matchedRouteCount = "matched_route_count"
        case mergedRank = "merged_rank"
        case classification
        case explanation
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        if container.contains(.entry) {
            entry = try container.decode(AcrossMemoryEntry.self, forKey: .entry)
        } else {
            entry = try AcrossMemoryEntry(from: decoder)
        }
        reciprocalRankScore = try container.decodeIfPresent(Double.self, forKey: .reciprocalRankScore)
        matchedRouteCount = try container.decodeIfPresent(Int.self, forKey: .matchedRouteCount) ?? 0
        mergedRank = try container.decodeIfPresent(Int.self, forKey: .mergedRank)
        classification = try container.decodeIfPresent(MemoryClassification.self, forKey: .classification)
        routeContributions = try container.decodeIfPresent(MemoryRetrievalExplanation.self, forKey: .explanation)?.routeContributions ?? []
    }
}

struct MemoryClassification: Decodable, Equatable {
    let primarySchema: String?
    let schemas: [String]

    enum CodingKeys: String, CodingKey {
        case primarySchema = "primary_schema"
        case schemas
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        primarySchema = try container.decodeIfPresent(String.self, forKey: .primarySchema)
        schemas = try container.decodeIfPresent([String].self, forKey: .schemas) ?? []
    }
}

struct MemoryRetrievalExplanation: Decodable, Equatable {
    let routeContributions: [MemoryRouteContribution]

    enum CodingKeys: String, CodingKey {
        case routeContributions
    }
}

struct MemoryRouteContribution: Decodable, Equatable, Identifiable {
    let route: MemoryRetrievalRoute
    let rank: Int
    let routeWeight: Double?
    let routeScore: Double?
    let reciprocalRankContribution: Double?

    var id: String { "\(route.rawValue)-\(rank)" }

    enum CodingKeys: String, CodingKey {
        case route
        case rank
        case routeWeight = "route_weight"
        case routeScore = "route_score"
        case reciprocalRankContribution = "reciprocal_rank_contribution"
    }
}

struct MemoryRouteResult: Decodable, Equatable, Identifiable {
    let route: MemoryRetrievalRoute
    let resultCount: Int
    let projectionUsed: Bool?

    var id: String { route.rawValue }

    enum CodingKeys: String, CodingKey {
        case route
        case resultCount = "result_count"
        case projectionUsed = "projection_used"
    }
}

struct MemoryImproveResponse: Decodable, Equatable {
    let status: String?
    let approvalRequired: Bool
    let sourceCount: Int
    let rejectedSourceCount: Int
    let clusterCount: Int
    let proposalCount: Int
    let duplicateProposalCount: Int
    let proposals: [MemoryDistillationProposal]

    enum CodingKeys: String, CodingKey {
        case status
        case approvalRequired = "approval_required"
        case sourceCount = "source_count"
        case rejectedSourceCount = "rejected_source_count"
        case clusterCount = "cluster_count"
        case proposalCount = "proposal_count"
        case duplicateProposalCount = "duplicate_proposal_count"
        case proposals
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        status = try container.decodeIfPresent(String.self, forKey: .status)
        approvalRequired = try container.decodeIfPresent(Bool.self, forKey: .approvalRequired) ?? true
        sourceCount = try container.decodeIfPresent(Int.self, forKey: .sourceCount) ?? 0
        rejectedSourceCount = try container.decodeIfPresent(Int.self, forKey: .rejectedSourceCount) ?? 0
        clusterCount = try container.decodeIfPresent(Int.self, forKey: .clusterCount) ?? 0
        proposalCount = try container.decodeIfPresent(Int.self, forKey: .proposalCount) ?? 0
        duplicateProposalCount = try container.decodeIfPresent(Int.self, forKey: .duplicateProposalCount) ?? 0
        proposals = try container.decodeIfPresent([MemoryDistillationProposal].self, forKey: .proposals) ?? []
    }
}

struct MemoryDistillationProposal: Decodable, Equatable, Identifiable {
    let memory: AcrossMemoryEntry
    let proposal: MemoryDistilledPayload

    var id: String { memory.id }
}

struct MemoryDistilledPayload: Decodable, Equatable {
    let memorySchema: String?
    let distilledText: String
    let governance: MemoryDistillationGovernance?
    let provenance: MemoryProvenance

    enum CodingKeys: String, CodingKey {
        case memorySchema = "memory_schema"
        case distilledText = "distilled_text"
        case governance
        case provenance
    }

    static func decode(from text: String) -> Self? {
        guard let data = text.data(using: .utf8) else { return nil }
        return try? JSONDecoder().decode(Self.self, from: data)
    }
}

struct MemoryDistillationGovernance: Decodable, Equatable {
    let status: String?
    let approvalRequired: Bool
    let rollbackSupported: Bool

    enum CodingKeys: String, CodingKey {
        case status
        case approvalRequired = "approval_required"
        case rollbackSupported = "rollback_supported"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        status = try container.decodeIfPresent(String.self, forKey: .status)
        approvalRequired = try container.decodeIfPresent(Bool.self, forKey: .approvalRequired) ?? true
        rollbackSupported = try container.decodeIfPresent(Bool.self, forKey: .rollbackSupported) ?? false
    }
}

struct MemoryProvenance: Decodable, Equatable {
    let sourceCount: Int
    let sources: [MemoryProvenanceSource]

    enum CodingKeys: String, CodingKey {
        case sourceCount = "source_count"
        case sources
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        sources = try container.decodeIfPresent([MemoryProvenanceSource].self, forKey: .sources) ?? []
        sourceCount = try container.decodeIfPresent(Int.self, forKey: .sourceCount) ?? sources.count
    }
}

struct MemoryProvenanceSource: Decodable, Equatable, Identifiable {
    let memoryId: String
    let type: String?
    let status: String?
    let scope: String?

    var id: String { memoryId }

    enum CodingKeys: String, CodingKey {
        case memoryId = "memory_id"
        case type
        case status
        case scope
    }
}

struct MemoryRollbackResponse: Decodable, Equatable {
    let proposalId: String
    let status: String
    let restoredSourceIds: [String]
    let missingSourceIds: [String]

    enum CodingKeys: String, CodingKey {
        case proposalId = "proposal_id"
        case status
        case restoredSourceIds = "restored_source_ids"
        case missingSourceIds = "missing_source_ids"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        proposalId = try container.decode(String.self, forKey: .proposalId)
        status = try container.decode(String.self, forKey: .status)
        restoredSourceIds = try container.decodeIfPresent([String].self, forKey: .restoredSourceIds) ?? []
        missingSourceIds = try container.decodeIfPresent([String].self, forKey: .missingSourceIds) ?? []
    }
}

private struct MemorySearchResultEnvelope: Decodable {
    let entry: AcrossMemoryEntry
}
