import SwiftUI

struct HomeView: View {
    @State private var count: Int = 0

    var body: some View {
        NavigationStack {
            VStack(spacing: 16) {
                Image("logo")
                Text(LocalizedStringKey("home.title"))
                Button("Open detail") { count += 1 }
            }
            .padding(24)
            .navigationTitle("Home")
        }
    }
}
