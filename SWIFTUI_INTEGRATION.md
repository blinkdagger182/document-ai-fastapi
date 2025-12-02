# SwiftUI Integration Guide

This guide shows how to integrate the DocumentAI backend with your SwiftUI app.

## API Base URL

```swift
let API_BASE_URL = "https://your-api.run.app/api/v1"
// For local development: "http://localhost:8080/api/v1"
```

## Data Models

```swift
import Foundation

// MARK: - Enums
enum DocumentStatus: String, Codable {
    case imported
    case processing
    case ready
    case filling
    case filled
    case failed
}

enum FieldType: String, Codable {
    case text
    case multiline
    case checkbox
    case date
    case number
    case signature
    case unknown
}

enum FieldSource: String, Codable {
    case manual
    case autofill
    case ai
}

// MARK: - Response Models
struct DocumentSummary: Codable, Identifiable {
    let id: UUID
    let fileName: String
    let mimeType: String
    let status: DocumentStatus
    let pageCount: Int?
    let createdAt: Date
    let updatedAt: Date
}

struct InitUploadResponse: Codable {
    let documentId: UUID
    let document: DocumentSummary
}

struct ProcessDocumentResponse: Codable {
    let documentId: UUID
    let status: DocumentStatus
}

struct FieldComponent: Codable, Identifiable {
    let id: UUID
    let fieldId: UUID
    let type: FieldType
    let label: String
    let placeholder: String?
    let pageIndex: Int
    let defaultValue: String?
    let options: [String]?
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

struct DownloadResponse: Codable {
    let documentId: UUID
    let filledPdfUrl: String
}

// MARK: - Request Models
struct FieldValueInput: Codable {
    let fieldRegionId: UUID
    let value: String
    let source: FieldSource
}

struct SubmitValuesRequest: Codable {
    let values: [FieldValueInput]
}
```

## API Service

```swift
import Foundation

class DocumentAIService: ObservableObject {
    private let baseURL: String
    private let session: URLSession
    
    init(baseURL: String = API_BASE_URL) {
        self.baseURL = baseURL
        
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 300
        config.timeoutIntervalForResource = 600
        self.session = URLSession(configuration: config)
    }
    
    // MARK: - Upload Document
    func uploadDocument(fileURL: URL) async throws -> InitUploadResponse {
        let url = URL(string: "\(baseURL)/documents/init-upload")!
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        
        let boundary = UUID().uuidString
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        
        let fileData = try Data(contentsOf: fileURL)
        let fileName = fileURL.lastPathComponent
        let mimeType = fileURL.pathExtension == "pdf" ? "application/pdf" : "image/jpeg"
        
        var body = Data()
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"\(fileName)\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: \(mimeType)\r\n\r\n".data(using: .utf8)!)
        body.append(fileData)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        
        request.httpBody = body
        
        let (data, response) = try await session.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            throw APIError.invalidResponse
        }
        
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return try decoder.decode(InitUploadResponse.self, from: data)
    }
    
    // MARK: - Process Document
    func processDocument(documentId: UUID) async throws -> ProcessDocumentResponse {
        let url = URL(string: "\(baseURL)/documents/\(documentId.uuidString)/process")!
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        
        let (data, _) = try await session.data(for: request)
        
        let decoder = JSONDecoder()
        return try decoder.decode(ProcessDocumentResponse.self, from: data)
    }
    
    // MARK: - Get Document Details
    func getDocument(documentId: UUID) async throws -> DocumentDetailResponse {
        let url = URL(string: "\(baseURL)/documents/\(documentId.uuidString)")!
        
        let (data, _) = try await session.data(for: url)
        
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return try decoder.decode(DocumentDetailResponse.self, from: data)
    }
    
    // MARK: - Submit Values
    func submitValues(documentId: UUID, values: [FieldValueInput]) async throws {
        let url = URL(string: "\(baseURL)/documents/\(documentId.uuidString)/values")!
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let payload = SubmitValuesRequest(values: values)
        let encoder = JSONEncoder()
        request.httpBody = try encoder.encode(payload)
        
        let (_, _) = try await session.data(for: request)
    }
    
    // MARK: - Compose PDF
    func composePDF(documentId: UUID) async throws -> ProcessDocumentResponse {
        let url = URL(string: "\(baseURL)/documents/\(documentId.uuidString)/compose")!
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        
        let (data, _) = try await session.data(for: request)
        
        let decoder = JSONDecoder()
        return try decoder.decode(ProcessDocumentResponse.self, from: data)
    }
    
    // MARK: - Download Filled PDF
    func getDownloadURL(documentId: UUID) async throws -> String {
        let url = URL(string: "\(baseURL)/documents/\(documentId.uuidString)/download")!
        
        let (data, _) = try await session.data(for: url)
        
        let decoder = JSONDecoder()
        let response = try decoder.decode(DownloadResponse.self, from: data)
        return response.filledPdfUrl
    }
    
    // MARK: - Poll for Status
    func pollUntilReady(documentId: UUID, maxAttempts: Int = 60) async throws -> DocumentDetailResponse {
        for _ in 0..<maxAttempts {
            let detail = try await getDocument(documentId: documentId)
            
            switch detail.document.status {
            case .ready, .filled:
                return detail
            case .failed:
                throw APIError.processingFailed
            default:
                try await Task.sleep(nanoseconds: 2_000_000_000) // 2 seconds
            }
        }
        
        throw APIError.timeout
    }
}

enum APIError: Error {
    case invalidResponse
    case processingFailed
    case timeout
}
```

## Complete Flow Example

```swift
import SwiftUI

struct DocumentUploadView: View {
    @StateObject private var service = DocumentAIService()
    @State private var isProcessing = false
    @State private var currentDocument: DocumentDetailResponse?
    @State private var formData: [UUID: String] = [:]
    @State private var showFilePicker = false
    
    var body: some View {
        VStack {
            if let document = currentDocument {
                if document.document.status == .ready {
                    FormView(
                        components: document.components,
                        formData: $formData,
                        onSubmit: { await submitForm(documentId: document.document.id) }
                    )
                } else if document.document.status == .filled {
                    CompletedView(documentId: document.document.id)
                }
            } else {
                Button("Upload Document") {
                    showFilePicker = true
                }
            }
        }
        .fileImporter(
            isPresented: $showFilePicker,
            allowedContentTypes: [.pdf, .image],
            onCompletion: handleFileSelection
        )
        .overlay {
            if isProcessing {
                ProgressView("Processing...")
            }
        }
    }
    
    private func handleFileSelection(_ result: Result<URL, Error>) {
        Task {
            do {
                isProcessing = true
                
                guard let fileURL = try? result.get() else { return }
                
                // 1. Upload
                let uploadResponse = try await service.uploadDocument(fileURL: fileURL)
                
                // 2. Process
                _ = try await service.processDocument(documentId: uploadResponse.documentId)
                
                // 3. Poll until ready
                let detail = try await service.pollUntilReady(documentId: uploadResponse.documentId)
                
                currentDocument = detail
                isProcessing = false
                
            } catch {
                print("Error: \(error)")
                isProcessing = false
            }
        }
    }
    
    private func submitForm(documentId: UUID) async {
        do {
            isProcessing = true
            
            // Convert form data to API format
            let values = formData.map { fieldId, value in
                FieldValueInput(
                    fieldRegionId: fieldId,
                    value: value,
                    source: .manual
                )
            }
            
            // Submit values
            try await service.submitValues(documentId: documentId, values: values)
            
            // Compose PDF
            _ = try await service.composePDF(documentId: documentId)
            
            // Poll until filled
            let detail = try await service.pollUntilReady(documentId: documentId)
            
            currentDocument = detail
            isProcessing = false
            
        } catch {
            print("Error: \(error)")
            isProcessing = false
        }
    }
}

struct FormView: View {
    let components: [FieldComponent]
    @Binding var formData: [UUID: String]
    let onSubmit: () async -> Void
    
    var body: some View {
        Form {
            ForEach(components) { component in
                switch component.type {
                case .text, .number, .date:
                    TextField(component.label, text: binding(for: component.fieldId))
                case .multiline:
                    TextEditor(text: binding(for: component.fieldId))
                        .frame(height: 100)
                case .checkbox:
                    Toggle(component.label, isOn: boolBinding(for: component.fieldId))
                default:
                    TextField(component.label, text: binding(for: component.fieldId))
                }
            }
            
            Button("Submit") {
                Task {
                    await onSubmit()
                }
            }
        }
    }
    
    private func binding(for fieldId: UUID) -> Binding<String> {
        Binding(
            get: { formData[fieldId] ?? "" },
            set: { formData[fieldId] = $0 }
        )
    }
    
    private func boolBinding(for fieldId: UUID) -> Binding<Bool> {
        Binding(
            get: { formData[fieldId] == "true" },
            set: { formData[fieldId] = $0 ? "true" : "false" }
        )
    }
}

struct CompletedView: View {
    let documentId: UUID
    @StateObject private var service = DocumentAIService()
    @State private var downloadURL: String?
    
    var body: some View {
        VStack {
            Text("Document Completed!")
                .font(.title)
            
            if let url = downloadURL {
                ShareLink(item: URL(string: url)!) {
                    Label("Download PDF", systemImage: "arrow.down.doc")
                }
            }
            
            Button("Start New") {
                // Reset flow
            }
        }
        .task {
            downloadURL = try? await service.getDownloadURL(documentId: documentId)
        }
    }
}
```

## Testing

```swift
// For local testing, use ngrok or similar to expose localhost
// ngrok http 8080

// Then update API_BASE_URL to your ngrok URL
let API_BASE_URL = "https://your-ngrok-url.ngrok.io/api/v1"
```

## Production Checklist

- [ ] Update API_BASE_URL to production Cloud Run URL
- [ ] Add proper error handling and user feedback
- [ ] Implement retry logic for network failures
- [ ] Add loading states and progress indicators
- [ ] Handle background/foreground transitions
- [ ] Add analytics and crash reporting
- [ ] Test with various PDF sizes and formats
- [ ] Implement offline queue for uploads
- [ ] Add authentication if needed
