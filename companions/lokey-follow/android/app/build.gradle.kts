plugins { id("com.android.application"); kotlin("android") }
android {
    namespace = "net.lokey.follow"
    compileSdk = 35
    defaultConfig { applicationId = "net.lokey.follow"; minSdk = 26; targetSdk = 35; versionCode = 1; versionName = "0.1.0" }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
}
dependencies { implementation(project(":core")); implementation("androidx.work:work-runtime-ktx:2.10.0") }
