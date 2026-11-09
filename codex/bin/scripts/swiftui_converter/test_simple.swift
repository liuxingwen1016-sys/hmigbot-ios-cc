import SwiftUI

struct ContentView: View {
    @State private var count = 0
    @State private var message = "Hello"
    
    var body: some View {
        VStack(spacing: 20) {
            Text("Count: \(count)")
                .font(.title)
                .foregroundColor(.blue)
            
            Text(message)
            
            Button("Increment") {
                count += 1
            }
            .padding()
            .background(Color.green)
        }
    }
}
