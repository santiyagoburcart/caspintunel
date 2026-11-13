package app.smsconfirm.ui

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import app.smsconfirm.R
import app.smsconfirm.data.SendStatus
import app.smsconfirm.data.SmsLogEntity
import app.smsconfirm.databinding.ItemSmsLogBinding
import java.text.DateFormat
import java.util.Date

class SmsLogAdapter : ListAdapter<SmsLogEntity, SmsLogAdapter.VH>(DIFF) {

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val binding = ItemSmsLogBinding.inflate(LayoutInflater.from(parent.context), parent, false)
        return VH(binding)
    }

    override fun onBindViewHolder(holder: VH, position: Int) = holder.bind(getItem(position))

    class VH(private val binding: ItemSmsLogBinding) : RecyclerView.ViewHolder(binding.root) {
        fun bind(item: SmsLogEntity) {
            val ctx = binding.root.context
            binding.sender.text = item.sender
            binding.preview.text = item.body.take(80)
            binding.timestamp.text = DateFormat.getTimeInstance(DateFormat.SHORT).format(Date(item.receivedAtMillis))

            val (label, colorRes) = when (item.status) {
                SendStatus.SENT -> ctx.getString(R.string.log_status_sent) to R.color.status_ok
                SendStatus.FAILED -> ctx.getString(R.string.log_status_failed) to R.color.status_error
                SendStatus.PENDING -> ctx.getString(R.string.log_status_pending) to R.color.status_warning
            }
            binding.statusBadge.text = label
            binding.statusBadge.setTextColor(ctx.getColor(colorRes))
        }
    }

    companion object {
        private val DIFF = object : DiffUtil.ItemCallback<SmsLogEntity>() {
            override fun areItemsTheSame(old: SmsLogEntity, new: SmsLogEntity) = old.id == new.id
            override fun areContentsTheSame(old: SmsLogEntity, new: SmsLogEntity) = old == new
        }
    }
}
