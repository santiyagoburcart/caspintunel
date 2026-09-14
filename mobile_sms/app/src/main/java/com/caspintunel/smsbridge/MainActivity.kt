package com.caspintunel.smsbridge

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.caspintunel.smsbridge.data.Prefs
import com.caspintunel.smsbridge.databinding.ActivityMainBinding
import com.caspintunel.smsbridge.repo.SmsRepository
import com.caspintunel.smsbridge.service.SmsForegroundService
import com.caspintunel.smsbridge.ui.SmsLogAdapter
import kotlinx.coroutines.launch
import java.text.DateFormat
import java.util.Date

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var prefs: Prefs
    private lateinit var repo: SmsRepository
    private val adapter = SmsLogAdapter()

    private val requestPermissions = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { _ -> startServiceIfReady() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        prefs = Prefs(this)
        repo = SmsRepository.get(this)

        binding.recyclerLog.layoutManager = LinearLayoutManager(this)
        binding.recyclerLog.adapter = adapter
        repo.recentLog(20).observe(this) { rows ->
            adapter.submitList(rows)
            binding.emptyLabel.visibility = if (rows.isEmpty()) android.view.View.VISIBLE else android.view.View.GONE
        }

        binding.btnSettings.setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }
        binding.btnTestPing.setOnClickListener { runPing() }

        renderStatus()
    }

    override fun onResume() {
        super.onResume()
        renderStatus()
        if (!prefs.isConfigured()) {
            startActivity(Intent(this, SettingsActivity::class.java))
            return
        }
        ensurePermissionsThenStartService()
    }

    private fun renderStatus() {
        val configured = prefs.isConfigured()
        when {
            !configured -> {
                binding.statusDot.setBackgroundResource(R.drawable.dot_warning)
                binding.statusTitle.text = getString(R.string.status_not_configured)
                binding.statusDetail.text = getString(R.string.status_not_configured_detail)
            }
            prefs.lastPingOk == true -> {
                binding.statusDot.setBackgroundResource(R.drawable.dot_ok)
                binding.statusTitle.text = getString(R.string.status_connected)
                binding.statusDetail.text = statusDetailLine()
            }
            prefs.lastPingOk == false -> {
                binding.statusDot.setBackgroundResource(R.drawable.dot_error)
                binding.statusTitle.text = getString(R.string.status_error)
                binding.statusDetail.text = statusDetailLine()
            }
            else -> {
                binding.statusDot.setBackgroundResource(R.drawable.dot_warning)
                binding.statusTitle.text = getString(R.string.status_unknown)
                binding.statusDetail.text = getString(R.string.status_unknown_detail)
            }
        }
    }

    private fun statusDetailLine(): String {
        val when_ = if (prefs.lastPingAtMillis > 0) {
            DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT).format(Date(prefs.lastPingAtMillis))
        } else "—"
        return "${prefs.lastPingMessage}  ·  $when_"
    }

    private fun runPing() {
        binding.btnTestPing.isEnabled = false
        lifecycleScope.launch {
            repo.ping()
            renderStatus()
            binding.btnTestPing.isEnabled = true
        }
    }

    private fun ensurePermissionsThenStartService() {
        val needed = requiredPermissions().filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (needed.isEmpty()) {
            startServiceIfReady()
        } else {
            requestPermissions.launch(needed.toTypedArray())
        }
    }

    private fun requiredPermissions(): List<String> {
        val perms = mutableListOf(Manifest.permission.RECEIVE_SMS, Manifest.permission.READ_PHONE_STATE)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            perms += Manifest.permission.POST_NOTIFICATIONS
        }
        return perms
    }

    private fun startServiceIfReady() {
        if (!prefs.isConfigured()) return
        val hasSms = ContextCompat.checkSelfPermission(this, Manifest.permission.RECEIVE_SMS) ==
            PackageManager.PERMISSION_GRANTED
        if (!hasSms) return
        val intent = Intent(this, SmsForegroundService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            ContextCompat.startForegroundService(this, intent)
        } else {
            startService(intent)
        }
    }
}
