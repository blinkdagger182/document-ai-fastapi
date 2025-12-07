# SwiftUI Integration Guide

## API Base URL

```swift
let API_BASE_URL = "https://your-api.run.app/api/v1"
```

## Data Models

```swift
import Foundation

enum DocumentStatus: String, Codable {
    case imported, processing, ready, filling, filled, failed
}

enum FieldType: String, Codable {
    case text, multiline, checkbox, date, number, signature, unknown
}

struct DocumentSummary: Codable, Identifiable {
    let id: UUID
    let fileName: String
    let mimeType: String
    let status: DocumentStatus
    let pageCount: Int?
    let createdAt: Date
    let updatedAt: Date
}

struct FieldComponent: Codable, Identifiable {
    let id: UUID
    let fieldId: UUID
    let type: FieldType
    let label: String
    let placeholder: String?
    let pageIndex: Int
}

struct FieldRegionDTO: Codable, Identifiable {
    let id: UUID
    let pageIndex: Int
    let x: Double
    let y: Double
    let width: Double
    let height: Double
    let fieldType: FieldType
    let label: String
    let confidence: Double
}

struct DocumentDetailResponse: Codable {
    let document: DocumentSummary
    let components: [FieldComponent]
    let fieldMap: [String: FieldRegionDTO]
}

struct FieldValueInput: Codable {
    let fieldRegionId: UUID
    let value: String
    let source: String // "manual", "autofill", "ai"
}
```

## API Service

```swift
class DocumentAIService: ObservableObject {
    private let baseURL: String
    
    init(baseURL: String = API_BASE_URL) {
        self.baseURL = baseURL
    }
    
    // Upload Document
    func uploadDocument(fileURL: URL) async throws -> UUID {
        let url = URL(string: "\(baseURL)/documents/init-upload")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        
        let boundary = UUID().uuidString
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        
        let fileData = try Data(contentsOf: fileURL)
        var body = Data()
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"\(fileURL.lastPathComponent)\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: application/pdf\r\n\r\n".data(using: .utf8)!)
        body.append(fileData)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        request.httpBody = body
        
        let (data, _) = try await URLSession.shared.data(for: request)
        let response = try JSONDecoder().decode(InitUploadResponse.self, from: data)
        return response.documentId
    }
    
    // Process Document
    func processDocument(documentId: UUID) async throws {
        let url = URL(string: "\(baseURL)/documents/\(documentId)/process")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        let _ = try await URLSession.shared.data(for: request)
    }
    
    // Get Document Details
    func getDocument(documentId: UUID) async throws -> DocumentDetailResponse {
        let url = URL(string: "\(baseURL)/documents/\(documentId)")!
        let (data, _) = try await URLSession.shared.data(from: url)
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return try decoder.decode(DocumentDetailResponse.self, from: data)
    }
    
    // Poll Until Ready
    func pollUntilReady(documentId: UUID) async throws -> DocumentDetailResponse {
        for _ in 0..<60 {
            let detail = try await getDocument(documentId: documentId)
            if detail.document.status == .ready || detail.document.status == .filled {
                return detail
            }
            if detail.document.status == .failed {
                throw NSError(domain: "DocumentAI", code: -1)
            }
            try await Task.sleep(nanoseconds: 2_000_000_000)
        }
        throw NSError(domain: "DocumentAI", code: -2) // Timeout
    }
    
    // Submit Values
    func submitValues(documentId: UUID, values: [FieldValueInput]) async throws {
        let url = URL(string: "\(baseURL)/documents/\(documentId)/values")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(["values": values])
        let _ = try await URLSession.shared.data(for: request)
    }
    
    // Compose PDF
    func composePDF(documentId: UUID) async throws {
        let url = URL(string: "\(baseURL)/documents/\(documentId)/compose")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        let _ = try await URLSession.shared.data(for: request)
    }
    
    // Get Download URL
    func getDownloadURL(documentId: UUID) async throws -> String {
        let url = URL(string: "\(baseURL)/documents/\(documentId)/download")!
        let (data, _) = try await URLSession.shared.data(from: url)
        let response = try JSONDecoder().decode(DownloadResponse.self, from: data)
        return response.filledPdfUrl
    }
}

struct InitUploadResponse: Codable {
    let documentId: UUID
}

struct DownloadResponse: Codable {
    let filledPdfUrl: String
}
```

## Complete Flow Example

```swift
// 1. Upload
let documentId = try await service.uploadDocument(fileURL: pdfURL)

// 2. Process
try await service.processDocument(documentId: documentId)

// 3. Poll until ready
let detail = try await service.pollUntilReady(documentId: documentId)

// 4. User fills form using detail.components

// 5. Submit values
let values = formData.map { FieldValueInput(fieldRegionId: $0.key, value: $0.value, source: "manual") }
try await service.submitValues(documentId: documentId, values: values)

// 6. Compose PDF
try await service.composePDF(documentId: documentId)

// 7. Get download URL
let downloadURL = try await service.getDownloadURL(documentId: documentId)
```
